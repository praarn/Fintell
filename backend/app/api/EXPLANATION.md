# backend/app/api/ — explanation

One FastAPI router per resource. Every function here is a thin wrapper:
validate/deserialize the request (Pydantic), call one `services/`
function, translate its exceptions to HTTP status codes, return a
response schema. No business logic lives in this folder — see
[`../services/EXPLANATION.md`](../services/EXPLANATION.md) for that.
Full rationale: root [`IMPLEMENTATION.md`](../../../IMPLEMENTATION.md) §5.

## Files

| File | Routes | Notes |
| --- | --- | --- |
| `health.py` | `GET /health` | liveness only, no DB |
| `auth.py` | `/auth/register`, `/login`, `/refresh`, `/logout`, `/me`, `/sessions`, `/activity` | rate-limited register/login; refresh-token rotation with reuse detection; every auth-relevant outcome writes an `audit_log` row |
| `statements.py` | `/statements/upload`, list, detail, download, delete, stats | rate-limited upload; accepts any file, never rejects on content — an unparseable file becomes a `failed_needs_manual` statement, not a 4xx |
| `transactions.py` | unified `GET /transactions`, `/split`, `/{id}/category`, `/spending/*`, `/recurring` | the cross-statement, cross-account transaction surface |
| `accounts.py` | `POST/GET /accounts` | simple CRUD, no update/delete yet |
| `anomalies.py` | `/anomalies`, `/detect`, `/stats`, `/{id}/dismiss` | serializes `(AnomalyFlag, Transaction)` pairs into one response shape |
| `ask.py` | `POST /ask`, `GET /ask/history` | natural-language question → `text_to_sql.service.answer_question` |
| `admin.py` | `/admin/llm-stats`, `/metrics`, `/promotion-job/run` | **not real RBAC** — gated behind ordinary auth like everything else; the data is system-wide but not sensitive per-user |
| `deps.py` | — | `get_current_user`, `get_current_family_id` (decode the bearer JWT, load the `User`); shared by every router above except `health.py` |

## Notes

- **Dependency direction is one-way**: `api/` → `services/` → `models/` +
  `core/`. Routers never touch the ORM or business rules directly.
- Auth is a single `HTTPBearer` dependency (`deps.get_current_user`) —
  there's no cookie session, no CSRF surface.
- Rate limiting (`auth_rate_limit`, `upload_rate_limit` from
  `core/rate_limit.py`) is applied per-route via `dependencies=[...]`,
  not globally.
- Every router that mutates user-visible state that matters for security
  (login, upload, session revocation) also calls `audit_service.record`.
