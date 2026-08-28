# Fintell — Personal Finance Statement Intelligence

Upload a bank statement in whatever shape your bank exports it — CSV, TSV or
plain text, a PDF (real or scanned), or a photo of a paper statement — any
column order, any date format, negative-for-debit or separate debit/credit
columns — and get back categorized transactions, spending views, anomaly flags,
and a natural-language "ask your finances" box. Any file type is accepted;
anything the parser can't read is logged for manual review, never rejected
outright.

The guiding principle throughout is **defensible over impressive**: deterministic
code does the work wherever it can, an LLM is used only where nothing else will
do, and every automated decision is logged so you can see why it was made.

For the full design rationale — every table, every tech choice and the
alternatives rejected, the parsing/categorization/anomaly/text-to-SQL internals,
the test strategy — see **[IMPLEMENTATION.md](./IMPLEMENTATION.md)**.

## Stack

- **Frontend:** Next.js (App Router, TypeScript, Tailwind)
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy 2 (async), managed with `uv`
- **Database:** PostgreSQL (no pgvector — see "text-to-SQL, not RAG" below)
- **ML:** scikit-learn `IsolationForest` for anomaly detection
- **Infra:** Docker Compose (dev + a production file behind Caddy), Alembic
  migrations, GitHub Actions (lint → pytest with a Postgres service → frontend
  build → `docker compose build`)

## Local development

```bash
# backend
cd backend && cp .env.example .env && uv sync
uv run alembic upgrade head
uv run python scripts/seed_merchant_lookup.py    # starter merchant→category rules
uv run python scripts/seed_demo.py               # demo user + synthetic multi-bank history
uv run uvicorn app.main:app --reload

# frontend
cd frontend && cp .env.local.example .env.local && npm install && npm run dev
```

Or the whole stack: `docker compose up --build` (backend on :8000, frontend on
:3000, migrations run automatically). The seed script creates
`demo@fintell.app` / `demo-password-123` with six months of synthetic
transactions across three "banks" in three different statement layouts. All seed
data is generated — no real financial data.

```bash
cd backend && uv run pytest        # ~146 tests, needs a local Postgres
```

Every command — Docker and local — is collected in **[commands.md](./commands.md)**.

## Deployment

- **Free**, no card: `render.yaml` is a Render Blueprint — *New → Blueprint →
  this repo → Apply* stands up a free Postgres + both services with HTTPS URLs.
- **VPS**: a production compose file runs the whole stack behind Caddy (automatic
  HTTPS) — `./deploy/deploy.sh` after filling in `.env.prod`.

Both are walked through in **[DEPLOY.md](./DEPLOY.md)**.

## Architecture decisions

### Tiered categorization — an LLM is the last resort, not the default

Categorization runs in three tiers and stops as soon as one is confident:

1. **Tier 1 — exact rules.** A normalized merchant string is looked up in
   `merchant_lookup` (`rule_exact`). Cheap, deterministic, auditable.
2. **Tier 2 — fuzzy match.** RapidFuzz against the same table above a score
   floor (`rule_fuzzy`), for `"AMZN Mktp US*2X9"` → `Amazon`.
3. **Tier 3 — batched LLM fallback.** Only merchants still unresolved are sent,
   **in one batched call per statement**, to an OpenAI-compatible model with a
   JSON-schema-constrained response (`llm`). Every call is written to
   `llm_batch_call` with token counts and an estimated cost; every per-merchant
   decision to `llm_decision_log`.

A **promotion job** watches `llm_decision_log`: once the same merchant has been
given the same category by the LLM `LLM_PROMOTION_MIN_OCCURRENCES` times, it is
promoted into `merchant_lookup` as a permanent Tier 1 rule. This is the actual
mechanism behind "the system gets cheaper as it runs" — the LLM teaches the
deterministic layer and then stops being asked.

`transactions.categorization_method` records which tier resolved each row, so the
"resolved without the LLM" number is measured, not asserted.

### Fingerprint-based bank profiles, not name-based

A statement's layout is identified by a **structural fingerprint** (header tokens,
column count, delimiter, date-format signature) rather than a bank name the user
typed. The first time a layout is seen it goes through full cold detection
(column classification, sign-convention inference); the resolved mapping is saved
as a `bank_profile` keyed by that fingerprint. The next statement with the same
structure — even from a different bank, or with the bank name absent — reuses the
profile and skips detection. `statements.parse_method` is `cold_detection` or
`profile_reuse`.

### Anomaly detection with explainability

A per-user `IsolationForest` over amount / category / frequency / merchant-novelty
features. Below `ANOMALY_MIN_TRANSACTIONS` of history a user's model isn't fit at
all (you can't call something unusual with nothing to compare it to). Each flag
carries the feature(s) that drove it, surfaced as plain text ("$1,180 is ~19×
your typical groceries charge"). Dismissing a flag feeds back as a suppressed
signature, so a dismissed *soft* pattern (novel merchant) stays quiet while a
dismissed merchant still surfaces on a genuinely large charge. Tested against a
synthetic history with two injected anomalies — the suite asserts **recall = 1.0**
on the injected set with a precision floor.

### "Ask your finances" — text-to-SQL, not RAG

Transaction question-answering is a **structured-data** problem, not a semantic
retrieval one. Embedding numeric rows and retrieving by similarity throws away
exactly the precision a real query keeps. So there are no embeddings and no
vector store.

Instead: a fixed set of **reviewed, parameterized query templates**
(`total_spend_in_period`, `spend_by_category_in_period`, `top_merchants_in_period`,
`compare_spend_between_periods`, `monthly_spend_trend`, `largest_transactions`).
The LLM's *only* job is to pick one template and fill a flat, typed parameter
object — via JSON-schema-constrained structured output, so it literally cannot
name a template outside the set. Those params are then re-validated against the
chosen template's own Pydantic model before anything runs.

Security properties this buys:

- **No injection surface** — the LLM never emits SQL.
- **No cross-user leakage** — every template's query builder takes `user_id` as a
  direct argument and scopes on it itself; the parameter models are
  `extra="ignore"`, so an adversarial completion that stuffs a `user_id` into its
  params has it silently dropped. There's a test that proves exactly this.
- **Auditable** — every possible query the system can run is in one file, and
  `query_template_log` records which template ran (or that the question was
  declined) for every question asked.

When no template matches confidently, the app **says so** rather than guessing.
The honest "template-match rate" comes straight out of `query_template_log`.

### Auth — refresh-token rotation with reuse detection

Short-lived JWT access tokens; refresh tokens are **rotated on every use** and
the old one is invalidated immediately. Refresh tokens are grouped into a
per-login *family*. If a rotated-out token is ever presented again, that's treated
as possible theft: the **entire family is revoked** and the user must log in
again. Each session stores its device/user-agent/IP-at-creation; there's a
user-facing "active sessions" page to view and revoke individual devices. Only
SHA-256 hashes of refresh tokens are stored.

### Phase 8 hardening

- **Uploaded files are never served from a static path.** Access goes through
  `POST /statements/{id}/download-url`, which mints a short-lived (`5 min`
  default) HS256-signed token scoped to one owner and one statement; the
  `GET .../file?token=…` endpoint verifies signature, expiry, and that the token's
  statement id matches the path before streaming the file. (At-rest encryption of
  the blobs is the natural next step and is noted below.)
- **Rate limiting** on the auth endpoints (`login`, `register`, `refresh`) and
  `upload`, as an in-process fixed-window limiter keyed by client IP. No Redis —
  this is a single-process deployment. Honest caveat: behind multiple workers
  each worker holds its own window; a shared store (Redis) is the fix if this
  ever scales out.
- **Audit log.** `audit_log` records login success/failure, refresh-reuse
  detection, statement upload/delete/download, and session revocation, with IP
  and user-agent. Exposed per-user at `GET /auth/activity` and on the Profile
  page.

## Measured metrics

From a fresh `seed_demo.py` run in this repo's development database (synthetic
data; `LLM_API_KEY` unset, so Tier 3 does not run here):

| Metric | Value | Source |
| --- | --- | --- |
| Transactions categorized deterministically (Tier 1/2) | **100%** of merchant-bearing rows (`rule_exact` 398, `rule_fuzzy` 14) | `GET /admin/metrics` |
| Statements parsed via a learned bank profile | **71%** (15 of 21 processed) | `statements.parse_method` |
| Distinct bank-layout profiles learned | **6** | `bank_profile` |
| LLM calls / estimated cost | **0 / $0.00** in this environment (Tier 3 disabled without a key) | `llm_batch_call` |
| Anomaly detection recall on injected set | **1.0** (precision floor 0.4) | `test_anomaly_detection.py` |
| Text-to-SQL template-match rate | exercised by 13 tests with a mocked selector; live rate read from `query_template_log` | `GET /admin/metrics` |

The `/admin/metrics` endpoint (and the **Metrics** page in the UI) computes all
of these live, so the numbers move as real usage accrues. With a real LLM key
configured, the interesting number to watch is the Tier 3 escalation rate falling
over time as the promotion job moves merchants into `merchant_lookup`.

## Assumptions & simplifications

- **No admin/RBAC.** The `/admin/*` routes are gated behind ordinary auth. The
  metrics they expose are system-wide but not per-user-sensitive.
- **Uploaded files are stored plaintext on local disk.** Access is controlled
  (signed URLs, ownership checks) but the blobs themselves aren't encrypted at
  rest and aren't on object storage. Both are straightforward next steps.
- **Rate-limit and anomaly-suppression state are in-process**, so they reset on
  restart and aren't shared across workers.
- **"Spend" means negative amounts**, reported as positive magnitudes; income and
  transfers are excluded from spending views and from text-to-SQL totals.
- **Costs are estimated** from provider-agnostic per-token rates in config, not
  billed amounts.
