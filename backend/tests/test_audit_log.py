"""Phase 8 — the security audit trail.

Every sensitive action (login success/failure, refresh-reuse detection,
statement upload/delete/download, session revocation) lands one row in
`audit_log`, and `GET /auth/activity` is scoped to the calling user.
"""

from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit_log import AuditLog
from tests.conftest import FIXTURES_DIR

EMAIL = "audit-user@example.com"
PASSWORD = "correct-horse-battery-staple"


async def _register_and_login(client: AsyncClient, email: str = EMAIL) -> dict:
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    return (
        await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    ).json()


async def _upload(client: AsyncClient, filename: str = "csv_clean_standard.csv"):
    data = (FIXTURES_DIR / filename).read_bytes()
    return await client.post(
        "/statements/upload", files={"file": (filename, data, "text/csv")}
    )


async def test_login_success_and_failure_are_recorded(client: AsyncClient, db_session) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    await client.post("/auth/login", json={"email": EMAIL, "password": "wrong"})
    await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    rows = list((await db_session.scalars(select(AuditLog).order_by(AuditLog.created_at))).all())
    actions = [r.action for r in rows]
    assert "auth.login_failed" in actions
    assert "auth.login" in actions

    failed = next(r for r in rows if r.action == "auth.login_failed")
    assert failed.user_id is None  # a failed login has no authenticated user
    assert failed.target_id == EMAIL

    ok = next(r for r in rows if r.action == "auth.login")
    assert ok.user_id is not None


async def test_refresh_reuse_detection_is_recorded(client: AsyncClient, db_session) -> None:
    tokens = await _register_and_login(client)
    rotated = (
        await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).json()
    assert "refresh_token" in rotated

    # replay the rotated-out token
    await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    row = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "auth.refresh_reuse_detected")
    )
    assert row is not None
    assert row.target_type == "session_family"


async def test_statement_upload_and_delete_are_recorded(client: AsyncClient, db_session) -> None:
    tokens = await _register_and_login(client)
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"

    statement = (await _upload(client)).json()
    delete_response = await client.delete(f"/statements/{statement['id']}")
    assert delete_response.status_code == 204

    rows = list(
        (
            await db_session.scalars(
                select(AuditLog)
                .where(AuditLog.target_type == "statement")
                .order_by(AuditLog.created_at)
            )
        ).all()
    )
    assert [r.action for r in rows] == ["statement.upload", "statement.delete"]
    assert all(r.target_id == statement["id"] for r in rows)
    assert rows[0].detail_json["filename"] == "csv_clean_standard.csv"


async def test_activity_endpoint_is_user_scoped(client: AsyncClient) -> None:
    alice = await _register_and_login(client, email=EMAIL)
    bob = await _register_and_login(client, email="bob-audit@example.com")

    alice_activity = (
        await client.get(
            "/auth/activity", headers={"Authorization": f"Bearer {alice['access_token']}"}
        )
    ).json()
    bob_activity = (
        await client.get(
            "/auth/activity", headers={"Authorization": f"Bearer {bob['access_token']}"}
        )
    ).json()

    # Each sees only their own login event, nothing of the other's.
    assert all(item["action"] == "auth.login" for item in alice_activity)
    assert len(alice_activity) == 1
    assert len(bob_activity) == 1
    assert alice_activity[0]["id"] != bob_activity[0]["id"]


async def test_session_revocation_is_recorded(client: AsyncClient, db_session) -> None:
    tokens = await _register_and_login(client)
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    sessions = (await client.get("/auth/sessions")).json()
    family_id = sessions[0]["family_id"]

    await client.delete(f"/auth/sessions/{family_id}")

    row = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "auth.session_revoked")
    )
    assert row is not None
    assert row.target_id == family_id


async def test_delete_also_removes_the_stored_file(client: AsyncClient, tmp_path) -> None:
    tokens = await _register_and_login(client)
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    statement = (await _upload(client)).json()

    # the upload storage dir is monkeypatched to tmp_path by conftest
    files_before = list(Path(tmp_path).rglob("*"))
    assert any(f.is_file() for f in files_before)

    await client.delete(f"/statements/{statement['id']}")
    assert not any(f.is_file() for f in Path(tmp_path).rglob("*"))
