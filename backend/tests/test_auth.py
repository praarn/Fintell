from httpx import AsyncClient

EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery-staple"


async def _register_and_login(client: AsyncClient, email: str = EMAIL) -> dict:
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    response = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return response.json()


async def test_register_creates_user(client: AsyncClient) -> None:
    response = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert "id" in body
    assert "hashed_password" not in body


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    response = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 409


async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    response = await client.post("/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    assert response.status_code == 401


async def test_login_rejects_unknown_email(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


async def test_access_token_authorizes_protected_route(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)
    response = await client.get(
        "/auth/sessions", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200


async def test_protected_route_rejects_missing_or_bad_token(client: AsyncClient) -> None:
    assert (await client.get("/auth/sessions")).status_code == 401
    response = await client.get(
        "/auth/sessions", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


async def test_refresh_rotates_token_and_invalidates_old_one(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)
    old_refresh_token = tokens["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["refresh_token"] != old_refresh_token

    # The rotated-out token must not work a second time.
    replay = await client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert replay.status_code == 401


async def test_refresh_reuse_detection_revokes_entire_family(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)
    token_a = tokens["refresh_token"]

    first_refresh = await client.post("/auth/refresh", json={"refresh_token": token_a})
    assert first_refresh.status_code == 200
    token_b = first_refresh.json()["refresh_token"]

    # Replaying the already-rotated-out token A must be detected as reuse...
    reuse_attempt = await client.post("/auth/refresh", json={"refresh_token": token_a})
    assert reuse_attempt.status_code == 401
    assert "reuse" in reuse_attempt.json()["detail"].lower()

    # ...and must have revoked the *whole* family, including the otherwise-valid token B.
    token_b_attempt = await client.post("/auth/refresh", json={"refresh_token": token_b})
    assert token_b_attempt.status_code == 401


async def test_refresh_rejects_unknown_token(client: AsyncClient) -> None:
    response = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


async def test_logout_revokes_session(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)

    logout_response = await client.post(
        "/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout_response.status_code == 204

    refresh_after_logout = await client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_after_logout.status_code == 401


async def test_sessions_list_shows_each_device_and_flags_current(
    client: AsyncClient,
) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    session_1 = (
        await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    ).json()
    session_2 = (
        await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    ).json()

    response = await client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {session_1['access_token']}"},
    )
    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 2
    current_flags = [s["is_current"] for s in sessions]
    assert current_flags.count(True) == 1

    # sanity: the other session's token still independently authenticates.
    other_response = await client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {session_2['access_token']}"},
    )
    assert other_response.status_code == 200


async def test_revoke_session_only_kills_that_device(client: AsyncClient) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    session_1 = (
        await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    ).json()
    session_2 = (
        await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    ).json()

    sessions = (
        await client.get(
            "/auth/sessions",
            headers={"Authorization": f"Bearer {session_1['access_token']}"},
        )
    ).json()
    session_1_family_id = next(s["family_id"] for s in sessions if s["is_current"])

    revoke_response = await client.delete(
        f"/auth/sessions/{session_1_family_id}",
        headers={"Authorization": f"Bearer {session_1['access_token']}"},
    )
    assert revoke_response.status_code == 204

    # Session 1's refresh token is now dead...
    dead_refresh = await client.post(
        "/auth/refresh", json={"refresh_token": session_1["refresh_token"]}
    )
    assert dead_refresh.status_code == 401

    # ...but session 2 is untouched.
    alive_refresh = await client.post(
        "/auth/refresh", json={"refresh_token": session_2["refresh_token"]}
    )
    assert alive_refresh.status_code == 200


async def test_revoke_session_rejects_other_users_session(client: AsyncClient) -> None:
    alice_tokens = await _register_and_login(client, email=EMAIL)
    bob_tokens = await _register_and_login(client, email="bob@example.com")

    alice_sessions = (
        await client.get(
            "/auth/sessions",
            headers={"Authorization": f"Bearer {alice_tokens['access_token']}"},
        )
    ).json()
    alice_family_id = alice_sessions[0]["family_id"]

    response = await client.delete(
        f"/auth/sessions/{alice_family_id}",
        headers={"Authorization": f"Bearer {bob_tokens['access_token']}"},
    )
    assert response.status_code == 404
