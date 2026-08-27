"""Phase 8 — in-process rate limiting on the auth surface.

The autouse `_disable_rate_limiting` fixture in conftest turns the limiter
off for the rest of the suite; here we turn it back on and prove the
window actually bites.
"""

import pytest
from httpx import AsyncClient

import app.core.rate_limit as rate_limit_module


@pytest.fixture(autouse=True)
def _enable_rate_limiting(monkeypatch):
    monkeypatch.setattr(rate_limit_module.settings, "rate_limit_enabled", True)
    rate_limit_module.limiter.reset()
    yield
    rate_limit_module.limiter.reset()


async def test_login_is_rate_limited_after_the_window_fills(client: AsyncClient) -> None:
    # register shares the "auth" scope, so it consumes the first slot
    await client.post(
        "/auth/register", json={"email": "rl@example.com", "password": "correct-horse-battery"}
    )

    limit = rate_limit_module.settings.rate_limit_auth_max_requests
    statuses = []
    for _ in range(limit + 3):
        resp = await client.post(
            "/auth/login", json={"email": "rl@example.com", "password": "wrong-password"}
        )
        statuses.append(resp.status_code)

    # everything up to the window limit reaches the handler (401 bad creds);
    # once the per-IP window is full the limiter answers 429 without ever
    # calling the handler.
    assert set(statuses[: limit - 1]) == {401}
    assert set(statuses[limit:]) == {429}
    assert statuses.count(429) >= 3

    last = await client.post(
        "/auth/login", json={"email": "rl@example.com", "password": "wrong-password"}
    )
    assert last.status_code == 429
    assert last.headers.get("Retry-After") is not None


async def test_limiter_is_per_scope(client: AsyncClient) -> None:
    """Exhausting the auth window doesn't block an unrelated route."""
    for _ in range(rate_limit_module.settings.rate_limit_auth_max_requests + 2):
        await client.post(
            "/auth/login", json={"email": "x@example.com", "password": "nope"}
        )

    # health check has no limiter attached
    assert (await client.get("/health")).status_code == 200
