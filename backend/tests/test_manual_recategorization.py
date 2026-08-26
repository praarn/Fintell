from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR

SECOND_STATEMENT = (
    b"Date,Description,Amount\n"
    b"02/01/2024,Grocery Mart #4471,-31.00\n"
    b"02/03/2024,Some Other Merchant,-10.00\n"
)


async def _upload(client: AsyncClient, filename: str, content: bytes | None = None):
    data = content if content is not None else (FIXTURES_DIR / filename).read_bytes()
    return await client.post("/statements/upload", files={"file": (filename, data, "text/csv")})


async def test_manual_correction_updates_transaction(authed_client: AsyncClient) -> None:
    upload = (await _upload(authed_client, "csv_clean_standard.csv")).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    grocery_txn = next(t for t in transactions if "Grocery Mart" in t["raw_merchant"])
    assert grocery_txn["categorization_method"] is None  # not in the seed set

    response = await authed_client.patch(
        f"/transactions/{grocery_txn['id']}/category", json={"category": "groceries"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "groceries"
    assert body["categorization_method"] == "manual_user_correction"
    assert float(body["confidence"]) == 1.0


async def test_manual_correction_closes_the_loop_for_future_statements(
    authed_client: AsyncClient,
) -> None:
    upload = (await _upload(authed_client, "csv_clean_standard.csv")).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    grocery_txn = next(t for t in transactions if "Grocery Mart" in t["raw_merchant"])

    await authed_client.patch(
        f"/transactions/{grocery_txn['id']}/category", json={"category": "groceries"}
    )

    second_upload = (await _upload(authed_client, "second.csv", SECOND_STATEMENT)).json()
    second_transactions = (
        await authed_client.get(f"/statements/{second_upload['id']}/transactions")
    ).json()
    same_merchant_txn = next(t for t in second_transactions if "Grocery Mart" in t["raw_merchant"])
    assert same_merchant_txn["categorization_method"] == "rule_exact"
    assert same_merchant_txn["category"] == "groceries"


async def test_rejects_invalid_category(authed_client: AsyncClient) -> None:
    upload = (await _upload(authed_client, "csv_clean_standard.csv")).json()
    transactions = (await authed_client.get(f"/statements/{upload['id']}/transactions")).json()
    txn_id = transactions[0]["id"]

    response = await authed_client.patch(
        f"/transactions/{txn_id}/category", json={"category": "not-a-real-category"}
    )
    assert response.status_code == 422


async def test_cannot_recategorize_another_users_transaction(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "alice2@example.com", "password": "correct-horse-battery"}
    )
    alice_token = (
        await client.post(
            "/auth/login",
            json={"email": "alice2@example.com", "password": "correct-horse-battery"},
        )
    ).json()["access_token"]

    upload = await client.post(
        "/statements/upload",
        files={
            "file": (
                "csv_clean_standard.csv",
                (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes(),
                "text/csv",
            )
        },
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    txn = (
        await client.get(
            f"/statements/{upload.json()['id']}/transactions",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
    ).json()[0]

    await client.post(
        "/auth/register", json={"email": "bob2@example.com", "password": "correct-horse-battery"}
    )
    bob_token = (
        await client.post(
            "/auth/login", json={"email": "bob2@example.com", "password": "correct-horse-battery"}
        )
    ).json()["access_token"]

    response = await client.patch(
        f"/transactions/{txn['id']}/category",
        json={"category": "groceries"},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert response.status_code == 404
