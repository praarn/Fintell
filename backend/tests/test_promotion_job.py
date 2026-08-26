import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.models.llm_batch_call import LLMBatchCall
from app.models.llm_decision_log import LLMDecisionLog
from app.models.merchant_lookup import MerchantLookup
from app.services.categorization import tier3
from app.services.categorization.promotion import run_promotion_job


async def _seed_decision_log(db_session, cleaned_merchant: str, category: str, count: int) -> None:
    batch = LLMBatchCall(
        model_used="fake-model",
        merchant_count=count,
        prompt_tokens=10,
        completion_tokens=10,
        estimated_cost_usd=0.0001,
    )
    db_session.add(batch)
    await db_session.flush()

    for _ in range(count):
        db_session.add(
            LLMDecisionLog(
                raw_merchant=f"POS {uuid.uuid4().hex[:6]} {cleaned_merchant.upper()}",
                cleaned_merchant=cleaned_merchant,
                llm_category=category,
                confidence=0.9,
                model_used="fake-model",
                batch_id=batch.id,
            )
        )
    await db_session.commit()


async def test_promotion_happens_at_threshold(db_session) -> None:
    await _seed_decision_log(db_session, "acme widgets", "shopping", count=3)

    result = await run_promotion_job(db_session, min_occurrences=3)
    assert result["promoted_count"] == 1
    assert "acme widgets" in result["promoted_merchants"]

    lookup = await db_session.scalar(
        select(MerchantLookup).where(MerchantLookup.raw_pattern == "acme widgets")
    )
    assert lookup is not None
    assert lookup.category == "shopping"
    assert lookup.match_type == "llm_promotion"
    assert lookup.promoted_from_llm is True

    decisions = list(
        (
            await db_session.scalars(
                select(LLMDecisionLog).where(LLMDecisionLog.cleaned_merchant == "acme widgets")
            )
        ).all()
    )
    assert all(d.promoted for d in decisions)


async def test_no_promotion_below_threshold(db_session) -> None:
    await _seed_decision_log(db_session, "small vendor", "shopping", count=2)

    result = await run_promotion_job(db_session, min_occurrences=3)
    assert result["promoted_count"] == 0

    lookup = await db_session.scalar(
        select(MerchantLookup).where(MerchantLookup.raw_pattern == "small vendor")
    )
    assert lookup is None


async def test_no_promotion_when_categories_inconsistent(db_session) -> None:
    await _seed_decision_log(db_session, "ambiguous merchant", "shopping", count=2)
    await _seed_decision_log(db_session, "ambiguous merchant", "dining", count=2)

    result = await run_promotion_job(db_session, min_occurrences=3)
    assert result["promoted_count"] == 0

    lookup = await db_session.scalar(
        select(MerchantLookup).where(MerchantLookup.raw_pattern == "ambiguous merchant")
    )
    assert lookup is None


async def test_promoted_merchant_resolves_at_tier2_without_hitting_llm(
    authed_client: AsyncClient, db_session, monkeypatch
) -> None:
    await _seed_decision_log(db_session, "acme widgets", "shopping", count=3)
    await run_promotion_job(db_session, min_occurrences=3)

    async def _fail_if_called(merchants: list[str]):
        raise AssertionError("LLM should not be called for an already-promoted merchant")

    monkeypatch.setattr(tier3.settings, "llm_api_key", "test-key")
    monkeypatch.setattr(tier3, "categorize_merchants_batch", _fail_if_called)

    csv_content = b"Date,Description,Amount\n01/03/2024,Acme Widgets,-25.00\n"
    upload = (
        await authed_client.post(
            "/statements/upload", files={"file": ("t.csv", csv_content, "text/csv")}
        )
    ).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()

    assert transactions[0]["categorization_method"] == "rule_exact"
    assert transactions[0]["category"] == "shopping"


async def test_promotion_job_endpoint_is_triggerable(
    authed_client: AsyncClient, db_session
) -> None:
    await _seed_decision_log(db_session, "acme widgets", "shopping", count=3)

    response = await authed_client.post("/admin/promotion-job/run")
    assert response.status_code == 200
    body = response.json()
    assert body["promoted_count"] == 1
    assert "acme widgets" in body["promoted_merchants"]
