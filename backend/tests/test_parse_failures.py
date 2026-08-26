from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR


async def test_malformed_rows_logged_and_statement_marked_with_warnings(
    authed_client: AsyncClient,
) -> None:
    data = (FIXTURES_DIR / "csv_malformed_rows.csv").read_bytes()
    upload = await authed_client.post(
        "/statements/upload", files={"file": ("csv_malformed_rows.csv", data, "text/csv")}
    )
    body = upload.json()
    assert body["parse_status"] == "parsed_with_warnings"
    assert body["row_count_parsed"] == 8
    assert body["row_count_failed"] == 2

    failures = (await authed_client.get(f"/statements/{body['id']}/parse-failures")).json()
    assert len(failures) == 2
    reason_codes = {f["reason_code"] for f in failures}
    assert reason_codes == {"unparseable_date", "unparseable_amount"}
    for failure in failures:
        assert failure["row_index"] is not None
        assert failure["raw_line_text"]
