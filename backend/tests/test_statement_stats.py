from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR

VARIANT_CSV = (
    b"date , DESCRIPTION,amount\n"
    b"02/01/2024,Bookstore Purchase,-22.10\n"
    b"02/03/2024,Freelance Payment,900.00\n"
)


async def _upload(client: AsyncClient, filename: str, content: bytes | None = None):
    data = content if content is not None else (FIXTURES_DIR / filename).read_bytes()
    return await client.post("/statements/upload", files={"file": (filename, data, "text/csv")})


async def test_pct_profile_reuse_computed_correctly(authed_client: AsyncClient) -> None:
    await _upload(authed_client, "csv_clean_standard.csv")  # cold_detection
    await _upload(authed_client, "variant_1.csv", VARIANT_CSV)  # profile_reuse
    await _upload(authed_client, "variant_2.csv", VARIANT_CSV)  # profile_reuse

    stats = (await authed_client.get("/statements/stats")).json()
    assert stats["total_statements_processed"] == 3
    assert stats["by_parse_method"]["cold_detection"] == 1
    assert stats["by_parse_method"]["profile_reuse"] == 2
    assert stats["pct_profile_reuse"] == round(2 / 3 * 100, 1)
    assert stats["distinct_bank_profiles"] == 1


async def test_stats_breakdown_by_structure_and_status(authed_client: AsyncClient) -> None:
    await _upload(authed_client, "csv_clean_standard.csv")
    await _upload(authed_client, "csv_malformed_rows.csv")

    stats = (await authed_client.get("/statements/stats")).json()
    assert stats["by_detected_structure"]["clean_csv"] == 2
    assert stats["by_parse_status"]["parsed_clean"] == 1
    assert stats["by_parse_status"]["parsed_with_warnings"] == 1
