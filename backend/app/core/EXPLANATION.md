# backend/app/core/ — explanation

Framework plumbing shared by everything else: settings, the DB engine,
auth primitives, and rate limiting. No business logic. Full rationale:
root [`IMPLEMENTATION.md`](../../../IMPLEMENTATION.md) §2, §6, §12.4.

## Files

| File | Role |
| --- | --- |
| `config.py` | `Settings` (pydantic-settings, reads `.env`) — every tunable in the app lives here as one field with an inline comment explaining what it gates; `get_settings()` is `@lru_cache`d so it's a singleton |
| `database.py` | the async SQLAlchemy engine, `async_session_factory`, the declarative `Base`, and `get_db()` — the FastAPI dependency every router/service session comes from |
| `security.py` | password hashing (bcrypt), access-token JWTs, and the signed short-lived download token used to serve uploaded files without a static route |
| `rate_limit.py` | in-process fixed-window limiter, keyed by `scope:client_ip`; ready-made `auth_rate_limit` / `upload_rate_limit` dependencies |

## Notes

- **No Redis.** `rate_limit.py` is an honest single-process,
  per-worker in-memory limiter — documented as such, not hidden. Fine
  for this deployment's scale; would need a shared store behind
  multiple workers.
- **Two distinct JWT types**, both HS256-signed with the same secret but
  a different `type` claim (`access` vs `download`) so one can never be
  replayed as the other — see `create_download_token` /
  `decode_download_token` in `security.py`.
- Only the refresh token's **hash** (SHA-256) is ever persisted
  (`hash_refresh_token`) — the raw token exists only in the response and
  the client's storage.
- `Settings` defaults are dev-safe placeholders (e.g. the JWT secret)
  and are expected to be overridden via `.env` in any real deployment.
