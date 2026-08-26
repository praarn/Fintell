from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR


async def test_create_and_list_accounts(authed_client: AsyncClient) -> None:
    response = await authed_client.post(
        "/accounts",
        json={"display_name": "Chase Checking", "bank_name": "Chase", "account_type": "checking"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Chase Checking"
    assert body["account_type"] == "checking"

    listing = (await authed_client.get("/accounts")).json()
    assert any(a["display_name"] == "Chase Checking" for a in listing)


async def test_invalid_account_type_rejected(authed_client: AsyncClient) -> None:
    response = await authed_client.post(
        "/accounts", json={"display_name": "Weird", "account_type": "not-a-real-type"}
    )
    assert response.status_code == 422


async def test_upload_links_to_explicit_account(authed_client: AsyncClient) -> None:
    account = (
        await authed_client.post(
            "/accounts", json={"display_name": "Chase Checking", "account_type": "checking"}
        )
    ).json()

    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    upload = (
        await authed_client.post(
            "/statements/upload",
            files={"file": ("t.csv", data, "text/csv")},
            data={"account_id": account["id"]},
        )
    ).json()
    assert upload["account_id"] == account["id"]

    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    assert all(t["account_id"] == account["id"] for t in transactions)


async def test_upload_with_unknown_account_id_is_rejected(authed_client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    response = await authed_client.post(
        "/statements/upload",
        files={"file": ("t.csv", data, "text/csv")},
        data={"account_id": fake_id},
    )
    assert response.status_code == 404


async def test_upload_without_account_auto_provisions_from_bank_hint(
    authed_client: AsyncClient,
) -> None:
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    upload = (
        await authed_client.post(
            "/statements/upload",
            files={"file": ("t.csv", data, "text/csv")},
            data={"bank_hint": "My Auto Bank"},
        )
    ).json()
    assert upload["account_id"] is not None

    accounts = (await authed_client.get("/accounts")).json()
    assert any(a["display_name"] == "My Auto Bank" for a in accounts)
