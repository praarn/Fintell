from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR


async def _upload(client: AsyncClient, filename: str = "csv_clean_standard.csv"):
    data = (FIXTURES_DIR / filename).read_bytes()
    return await client.post("/statements/upload", files={"file": (filename, data, "text/csv")})


async def test_unified_list_merges_across_statements(authed_client: AsyncClient) -> None:
    await _upload(authed_client)
    await _upload(authed_client, "csv_debit_credit_columns.csv")

    body = (await authed_client.get("/transactions")).json()
    assert body["total"] == 20
    assert len(body["items"]) == 20  # default page_size 50 covers both


async def test_pagination(authed_client: AsyncClient) -> None:
    await _upload(authed_client)

    page_1 = (await authed_client.get("/transactions", params={"page": 1, "page_size": 4})).json()
    page_2 = (await authed_client.get("/transactions", params={"page": 2, "page_size": 4})).json()

    assert page_1["total"] == 10
    assert len(page_1["items"]) == 4
    assert len(page_2["items"]) == 4
    assert {i["id"] for i in page_1["items"]}.isdisjoint({i["id"] for i in page_2["items"]})


async def test_filter_by_account(authed_client: AsyncClient) -> None:
    account_a = (
        await authed_client.post(
            "/accounts", json={"display_name": "Account A", "account_type": "checking"}
        )
    ).json()
    account_b = (
        await authed_client.post(
            "/accounts", json={"display_name": "Account B", "account_type": "savings"}
        )
    ).json()

    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    await authed_client.post(
        "/statements/upload",
        files={"file": ("a.csv", data, "text/csv")},
        data={"account_id": account_a["id"]},
    )
    await authed_client.post(
        "/statements/upload",
        files={"file": ("b.csv", data, "text/csv")},
        data={"account_id": account_b["id"]},
    )

    filtered = (
        await authed_client.get("/transactions", params={"account_id": account_a["id"]})
    ).json()
    assert filtered["total"] == 10
    assert all(t["account_id"] == account_a["id"] for t in filtered["items"])


async def test_search_by_merchant_text(authed_client: AsyncClient) -> None:
    await _upload(authed_client)

    results = (await authed_client.get("/transactions", params={"search": "Grocery"})).json()
    assert results["total"] == 1
    assert "Grocery" in results["items"][0]["raw_merchant"]


async def test_filter_by_category(authed_client: AsyncClient) -> None:
    upload = (await _upload(authed_client)).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    await authed_client.patch(
        f"/transactions/{transactions[0]['id']}/category", json={"category": "groceries"}
    )

    filtered = (await authed_client.get("/transactions", params={"category": "groceries"})).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["category"] == "groceries"


async def test_only_sees_own_transactions(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "u1@example.com", "password": "correct-horse-battery"}
    )
    token1 = (
        await client.post(
            "/auth/login", json={"email": "u1@example.com", "password": "correct-horse-battery"}
        )
    ).json()["access_token"]
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    await client.post(
        "/statements/upload",
        files={"file": ("t.csv", data, "text/csv")},
        headers={"Authorization": f"Bearer {token1}"},
    )

    await client.post(
        "/auth/register", json={"email": "u2@example.com", "password": "correct-horse-battery"}
    )
    token2 = (
        await client.post(
            "/auth/login", json={"email": "u2@example.com", "password": "correct-horse-battery"}
        )
    ).json()["access_token"]

    result = (
        await client.get("/transactions", headers={"Authorization": f"Bearer {token2}"})
    ).json()
    assert result["total"] == 0
