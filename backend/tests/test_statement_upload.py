from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


async def _upload(client: AsyncClient, filename: str, content_type: str = "text/csv"):
    return await client.post(
        "/statements/upload",
        files={"file": (filename, _read(filename), content_type)},
    )


async def test_upload_requires_auth(client: AsyncClient) -> None:
    response = await _upload(client, "csv_clean_standard.csv")
    assert response.status_code == 401


async def test_upload_happy_path(authed_client: AsyncClient) -> None:
    response = await _upload(authed_client, "csv_clean_standard.csv")
    assert response.status_code == 201
    body = response.json()
    assert body["file_type"] == "csv"
    assert body["detected_structure"] == "clean_csv"
    assert body["parse_status"] == "parsed_clean"
    assert body["row_count_parsed"] == 10
    assert body["row_count_failed"] == 0
    assert body["parse_method"] == "cold_detection"


async def test_rejects_unsupported_file_type(authed_client: AsyncClient) -> None:
    response = await authed_client.post(
        "/statements/upload",
        files={"file": ("statement.txt", b"not a real statement", "text/plain")},
    )
    assert response.status_code == 400


async def test_statement_list_and_detail_are_user_scoped(authed_client: AsyncClient) -> None:
    upload = await _upload(authed_client, "csv_clean_standard.csv")
    statement_id = upload.json()["id"]

    listing = await authed_client.get("/statements")
    assert listing.status_code == 200
    assert any(s["id"] == statement_id for s in listing.json())

    detail = await authed_client.get(f"/statements/{statement_id}")
    assert detail.status_code == 200

    transactions = await authed_client.get(f"/statements/{statement_id}/transactions")
    assert transactions.status_code == 200
    assert len(transactions.json()) == 10


async def test_cannot_access_another_users_statement(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "alice@example.com", "password": "correct-horse-battery"}
    )
    alice_login = await client.post(
        "/auth/login", json={"email": "alice@example.com", "password": "correct-horse-battery"}
    )
    alice_token = alice_login.json()["access_token"]

    upload = await client.post(
        "/statements/upload",
        files={"file": ("csv_clean_standard.csv", _read("csv_clean_standard.csv"), "text/csv")},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    statement_id = upload.json()["id"]

    await client.post(
        "/auth/register", json={"email": "bob@example.com", "password": "correct-horse-battery"}
    )
    bob_login = await client.post(
        "/auth/login", json={"email": "bob@example.com", "password": "correct-horse-battery"}
    )
    bob_token = bob_login.json()["access_token"]

    response = await client.get(
        f"/statements/{statement_id}", headers={"Authorization": f"Bearer {bob_token}"}
    )
    assert response.status_code == 404
