from httpx import AsyncClient

from tests.conftest import FIXTURES_DIR


async def _upload_and_get_grocery_txn(client: AsyncClient) -> dict:
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    upload = (
        await client.post("/statements/upload", files={"file": ("t.csv", data, "text/csv")})
    ).json()
    transactions = (await client.get(f"/statements/{upload['id']}/transactions")).json()
    return next(t for t in transactions if "Grocery Mart" in t["raw_merchant"])


async def test_split_transaction_success(authed_client: AsyncClient) -> None:
    txn = await _upload_and_get_grocery_txn(authed_client)
    assert txn["amount"] == "-54.23"

    response = await authed_client.patch(
        f"/transactions/{txn['id']}/category", json={"category": "groceries"}
    )  # give it a category first, splitting should clear it
    assert response.status_code == 200

    response = await authed_client.post(
        f"/transactions/{txn['id']}/split",
        json={
            "splits": [
                {"category": "groceries", "amount": "-40.00"},
                {"category": "other", "amount": "-14.23"},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["category"] is None
    assert body["categorization_method"] is None
    # Regression: is_split isn't a real column, it's computed at read time —
    # the split endpoint's own response must set it too, or a client acting
    # only on this response (not a follow-up list call) sees a stale value.
    assert body["is_split"] is True

    splits = (await authed_client.get(f"/transactions/{txn['id']}/splits")).json()
    assert len(splits) == 2
    assert {s["category"] for s in splits} == {"groceries", "other"}

    listing = (await authed_client.get("/transactions")).json()
    listed = next(t for t in listing["items"] if t["id"] == txn["id"])
    assert listed["is_split"] is True


async def test_split_amounts_must_sum_to_parent_amount(authed_client: AsyncClient) -> None:
    txn = await _upload_and_get_grocery_txn(authed_client)

    response = await authed_client.post(
        f"/transactions/{txn['id']}/split",
        json={
            "splits": [
                {"category": "groceries", "amount": "-40.00"},
                {"category": "other", "amount": "-10.00"},
            ]
        },
    )
    assert response.status_code == 422


async def test_split_requires_at_least_two_allocations(authed_client: AsyncClient) -> None:
    txn = await _upload_and_get_grocery_txn(authed_client)

    response = await authed_client.post(
        f"/transactions/{txn['id']}/split",
        json={"splits": [{"category": "groceries", "amount": "-54.23"}]},
    )
    assert response.status_code == 422


async def test_split_rejects_invalid_category(authed_client: AsyncClient) -> None:
    txn = await _upload_and_get_grocery_txn(authed_client)

    response = await authed_client.post(
        f"/transactions/{txn['id']}/split",
        json={
            "splits": [
                {"category": "groceries", "amount": "-40.00"},
                {"category": "not-a-real-category", "amount": "-14.23"},
            ]
        },
    )
    assert response.status_code == 422


async def test_unsplit_removes_splits(authed_client: AsyncClient) -> None:
    txn = await _upload_and_get_grocery_txn(authed_client)
    await authed_client.post(
        f"/transactions/{txn['id']}/split",
        json={
            "splits": [
                {"category": "groceries", "amount": "-40.00"},
                {"category": "other", "amount": "-14.23"},
            ]
        },
    )

    response = await authed_client.delete(f"/transactions/{txn['id']}/split")
    assert response.status_code == 200
    assert response.json()["is_split"] is False

    splits = (await authed_client.get(f"/transactions/{txn['id']}/splits")).json()
    assert splits == []


async def test_spending_by_category_reflects_split_allocations(authed_client: AsyncClient) -> None:
    txn = await _upload_and_get_grocery_txn(authed_client)
    await authed_client.post(
        f"/transactions/{txn['id']}/split",
        json={
            "splits": [
                {"category": "groceries", "amount": "-40.00"},
                {"category": "other", "amount": "-14.23"},
            ]
        },
    )

    spending = (await authed_client.get("/transactions/spending/by-category")).json()
    assert spending["by_category"]["groceries"] == "40.00"
    assert spending["by_category"]["other"] == "14.23"


async def test_cannot_split_another_users_transaction(client: AsyncClient) -> None:
    await client.post(
        "/auth/register", json={"email": "alice3@example.com", "password": "correct-horse-battery"}
    )
    alice_token = (
        await client.post(
            "/auth/login",
            json={"email": "alice3@example.com", "password": "correct-horse-battery"},
        )
    ).json()["access_token"]
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    upload = await client.post(
        "/statements/upload",
        files={"file": ("t.csv", data, "text/csv")},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    txn_id = (
        await client.get(
            f"/statements/{upload.json()['id']}/transactions",
            headers={"Authorization": f"Bearer {alice_token}"},
        )
    ).json()[0]["id"]

    await client.post(
        "/auth/register", json={"email": "bob3@example.com", "password": "correct-horse-battery"}
    )
    bob_token = (
        await client.post(
            "/auth/login", json={"email": "bob3@example.com", "password": "correct-horse-battery"}
        )
    ).json()["access_token"]

    response = await client.post(
        f"/transactions/{txn_id}/split",
        json={
            "splits": [
                {"category": "groceries", "amount": "-1.00"},
                {"category": "other", "amount": "-1.00"},
            ]
        },
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert response.status_code == 404
