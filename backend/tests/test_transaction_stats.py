from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR


async def test_categorization_stats_reflect_uncategorized_transactions(
    authed_client: AsyncClient,
) -> None:
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    await authed_client.post(
        "/statements/upload", files={"file": ("csv_clean_standard.csv", data, "text/csv")}
    )

    stats = (await authed_client.get("/transactions/stats")).json()
    assert stats["total_transactions"] == 10
    # None of csv_clean_standard's synthetic merchants are in the seed set.
    assert stats["by_categorization_method"]["unresolved"] == 10
    assert stats["pct_resolved_without_llm"] == 0.0


async def test_categorization_stats_after_manual_correction(authed_client: AsyncClient) -> None:
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    upload = (
        await authed_client.post(
            "/statements/upload", files={"file": ("csv_clean_standard.csv", data, "text/csv")}
        )
    ).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    await authed_client.patch(
        f"/transactions/{transactions[0]['id']}/category", json={"category": "groceries"}
    )

    stats = (await authed_client.get("/transactions/stats")).json()
    assert stats["by_categorization_method"]["manual_user_correction"] == 1
    assert stats["by_categorization_method"]["unresolved"] == 9
    assert stats["pct_resolved_without_llm"] == 10.0
