from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR

VARIANT_CSV = (
    b"date , DESCRIPTION,amount\n"
    b"02/01/2024,Bookstore Purchase,-22.10\n"
    b"02/03/2024,Freelance Payment,900.00\n"
    b"02/05/2024,Streaming Service,-9.99\n"
)


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


async def _upload(client: AsyncClient, filename: str, content: bytes | None = None):
    return await client.post(
        "/statements/upload",
        files={"file": (filename, content if content is not None else _read(filename), "text/csv")},
    )


async def test_first_upload_is_cold_detection(authed_client: AsyncClient) -> None:
    response = await _upload(authed_client, "csv_clean_standard.csv")
    body = response.json()
    assert body["parse_method"] == "cold_detection"
    assert body["bank_profile_id"] is not None


async def test_similar_layout_reuses_profile(authed_client: AsyncClient) -> None:
    first = (await _upload(authed_client, "csv_clean_standard.csv")).json()

    second = (await _upload(authed_client, "variant.csv", VARIANT_CSV)).json()
    assert second["parse_method"] == "profile_reuse"
    assert second["bank_profile_id"] == first["bank_profile_id"]
    assert second["row_count_parsed"] == 3


async def test_different_layout_creates_a_new_profile(authed_client: AsyncClient) -> None:
    first = (await _upload(authed_client, "csv_clean_standard.csv")).json()
    different = (await _upload(authed_client, "csv_debit_credit_columns.csv")).json()

    assert different["parse_method"] == "cold_detection"
    assert different["bank_profile_id"] != first["bank_profile_id"]


async def test_stats_reflect_profile_reuse(authed_client: AsyncClient) -> None:
    await _upload(authed_client, "csv_clean_standard.csv")
    await _upload(authed_client, "variant.csv", VARIANT_CSV)

    stats = (await authed_client.get("/statements/stats")).json()
    assert stats["distinct_bank_profiles"] >= 1
    assert stats["by_parse_method"].get("profile_reuse", 0) >= 1
    assert stats["by_parse_method"].get("cold_detection", 0) >= 1
    assert 0 < stats["pct_profile_reuse"] < 100
