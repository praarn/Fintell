"""A minimal in-process fixed-window rate limiter.

The spec calls for rate limiting on the auth and upload endpoints with
"no Redis". This project is a single-process deployment, so an in-memory
per-IP request log is enough — with the honest caveat (documented in the
README) that behind multiple workers each worker holds its own window.

Used as a FastAPI dependency:

    @router.post("/login", dependencies=[Depends(auth_rate_limit)])
"""

import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings

settings = get_settings()


class FixedWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = self._hits[key]
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= max_requests:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


limiter = FixedWindowLimiter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Build a dependency that allows `max_requests` per `window_seconds`
    per client IP for the given `scope`."""

    async def _dependency(request: Request) -> None:
        if not settings.rate_limit_enabled:
            return
        key = f"{scope}:{_client_ip(request)}"
        if not limiter.allow(key, max_requests, window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please slow down and try again shortly.",
                headers={"Retry-After": str(window_seconds)},
            )

    return _dependency


# Ready-made dependencies for the two rate-limited surfaces.
auth_rate_limit = Depends(
    rate_limit(
        "auth",
        settings.rate_limit_auth_max_requests,
        settings.rate_limit_auth_window_seconds,
    )
)
upload_rate_limit = Depends(
    rate_limit(
        "upload",
        settings.rate_limit_upload_max_requests,
        settings.rate_limit_upload_window_seconds,
    )
)
