from httpx import AsyncClient
from sqlalchemy import select

from app.models.llm_batch_call import LLMBatchCall
from app.models.llm_decision_log import LLMDecisionLog
from app.services.categorization import tier3
from app.services.categorization.llm_client import LLMCallResult, MerchantCategorization

CSV_WITH_UNKNOWN_MERCHANT = (
    b"Date,Description,Amount\n"
    b"01/03/2024,Totally Unrecognized Merchant Inc,-40.00\n"
    b"01/05/2024,Another Unknown Vendor Co,-15.00\n"
)


def _fake_llm(category: str = "shopping", confidence: float = 0.85):
    async def _call(merchants: list[str]) -> LLMCallResult:
        return LLMCallResult(
            categorizations=[
                MerchantCategorization(merchant=m, category=category, confidence=confidence)
                for m in merchants
            ],
            model_used="fake-model",
            prompt_tokens=120,
            completion_tokens=30,
        )

    return _call


async def test_llm_fallback_categorizes_unresolved_transactions(
    authed_client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr(tier3.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(tier3, "categorize_merchants_batch", _fake_llm())

    upload = (
        await authed_client.post(
            "/statements/upload",
            files={"file": ("t.csv", CSV_WITH_UNKNOWN_MERCHANT, "text/csv")},
        )
    ).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()

    assert all(t["categorization_method"] == "llm" for t in transactions)
    assert all(t["category"] == "shopping" for t in transactions)
    assert all(float(t["confidence"]) == 0.85 for t in transactions)


async def test_llm_call_skipped_when_no_api_key_configured(authed_client: AsyncClient) -> None:
    upload = (
        await authed_client.post(
            "/statements/upload",
            files={"file": ("t.csv", CSV_WITH_UNKNOWN_MERCHANT, "text/csv")},
        )
    ).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    assert all(t["categorization_method"] is None for t in transactions)


async def test_llm_failure_degrades_gracefully(authed_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(tier3.settings, "llm_api_key", "test-key")

    async def _raise(merchants: list[str]):
        raise RuntimeError("simulated API outage")

    monkeypatch.setattr(tier3, "categorize_merchants_batch", _raise)

    response = await authed_client.post(
        "/statements/upload",
        files={"file": ("t.csv", CSV_WITH_UNKNOWN_MERCHANT, "text/csv")},
    )
    assert response.status_code == 201  # upload itself never fails
    transactions = (
        await authed_client.get(f"/statements/{response.json()['id']}/transactions")
    ).json()
    assert all(t["categorization_method"] is None for t in transactions)


async def test_llm_decisions_and_batch_call_are_logged(
    authed_client: AsyncClient, monkeypatch, db_session
) -> None:
    monkeypatch.setattr(tier3.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(tier3, "categorize_merchants_batch", _fake_llm())

    await authed_client.post(
        "/statements/upload",
        files={"file": ("t.csv", CSV_WITH_UNKNOWN_MERCHANT, "text/csv")},
    )

    batch_calls = list((await db_session.scalars(select(LLMBatchCall))).all())
    assert len(batch_calls) == 1
    assert batch_calls[0].merchant_count == 2
    assert batch_calls[0].prompt_tokens == 120
    assert batch_calls[0].completion_tokens == 30
    assert batch_calls[0].estimated_cost_usd > 0

    decisions = list((await db_session.scalars(select(LLMDecisionLog))).all())
    assert len(decisions) == 2
    assert all(d.llm_category == "shopping" for d in decisions)
    assert all(d.batch_id == batch_calls[0].id for d in decisions)
    assert all(not d.promoted for d in decisions)


async def test_llm_stats_endpoint_reflects_usage(authed_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(tier3.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(tier3, "categorize_merchants_batch", _fake_llm())

    await authed_client.post(
        "/statements/upload",
        files={"file": ("t.csv", CSV_WITH_UNKNOWN_MERCHANT, "text/csv")},
    )

    stats = (await authed_client.get("/admin/llm-stats")).json()
    assert stats["total_batch_calls"] == 1
    assert stats["total_merchants_categorized"] == 2
    assert stats["total_prompt_tokens"] == 120
    assert stats["total_completion_tokens"] == 30
    assert stats["total_estimated_cost_usd"] > 0
