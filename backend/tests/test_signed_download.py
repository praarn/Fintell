"""Phase 8 — uploaded statement files are reachable only through a
short-lived signed URL minted for the owner, never a static path.
"""

import uuid

from httpx import AsyncClient

from app.core import security
from tests.conftest import FIXTURES_DIR

PASSWORD = "correct-horse-battery-staple"


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    tokens = (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()
    return tokens["access_token"]


async def _upload(client: AsyncClient, token: str) -> dict:
    data = (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    return (
        await client.post(
            "/statements/upload",
            files={"file": ("csv_clean_standard.csv", data, "text/csv")},
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()


async def test_owner_can_mint_a_url_and_fetch_the_file(client: AsyncClient) -> None:
    token = await _register_and_login(client, "dl-owner@example.com")
    statement = await _upload(client, token)

    minted = await client.post(
        f"/statements/{statement['id']}/download-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert minted.status_code == 200
    body = minted.json()
    assert body["expires_in_seconds"] > 0

    # the URL carries its own auth (a signed token) — no bearer header here
    fetched = await client.get(body["url"])
    assert fetched.status_code == 200
    assert fetched.content == (FIXTURES_DIR / "csv_clean_standard.csv").read_bytes()
    assert "csv_clean_standard.csv" in fetched.headers.get("content-disposition", "")


async def test_minting_a_url_requires_ownership(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner2@example.com")
    statement = await _upload(client, owner_token)

    other_token = await _register_and_login(client, "intruder@example.com")
    response = await client.post(
        f"/statements/{statement['id']}/download-url",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404


async def test_tampered_token_is_rejected(client: AsyncClient) -> None:
    token = await _register_and_login(client, "dl3@example.com")
    statement = await _upload(client, token)
    url = (
        await client.post(
            f"/statements/{statement['id']}/download-url",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()["url"]

    tampered = url[:-4] + "AAAA"
    assert (await client.get(tampered)).status_code == 403


async def test_expired_token_is_rejected(client: AsyncClient, monkeypatch) -> None:
    token = await _register_and_login(client, "dl4@example.com")
    statement = await _upload(client, token)

    # mint a token that expired a minute ago (expiry is checked before the
    # owner lookup, so the sub value doesn't need to be a real user)
    monkeypatch.setattr(security.settings, "download_url_ttl_seconds", -60)
    stale = security.create_download_token(uuid.UUID(statement["id"]), uuid.uuid4())
    monkeypatch.setattr(security.settings, "download_url_ttl_seconds", 300)

    response = await client.get(f"/statements/{statement['id']}/file?token={stale}")
    assert response.status_code == 403


async def test_token_for_one_statement_does_not_unlock_another(client: AsyncClient) -> None:
    token = await _register_and_login(client, "dl5@example.com")
    a = await _upload(client, token)
    b = await _upload(client, token)

    url_a = (
        await client.post(
            f"/statements/{a['id']}/download-url",
            headers={"Authorization": f"Bearer {token}"},
        )
    ).json()["url"]
    token_a = url_a.split("token=")[1]

    # point statement A's token at statement B's file id
    crossed = f"/statements/{b['id']}/file?token={token_a}"
    assert (await client.get(crossed)).status_code == 403


def test_download_token_roundtrip_and_type_guard() -> None:
    import uuid

    sid, uid = uuid.uuid4(), uuid.uuid4()
    tok = security.create_download_token(sid, uid)
    payload = security.decode_download_token(tok)
    assert payload["sid"] == str(sid)
    assert payload["sub"] == str(uid)

    # an access token must not be usable as a download token
    access = security.create_access_token(uid, uuid.uuid4())
    try:
        security.decode_download_token(access)
        raise AssertionError("expected a type-guard rejection")
    except Exception as exc:  # noqa: BLE001
        assert "download token" in str(exc)
