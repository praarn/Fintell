# Fintell — Implementation Notes

This is the deep-dive companion to the [README](./README.md). It documents
**what** is built, **how** it works, **why** each decision was made, and
**why the alternatives were rejected**. It is written to be read top to
bottom by someone who wants the whole picture, or dipped into by section.

The private product spec this was built against (`docs/`) is intentionally
kept out of version control.

---

## Table of contents

1. [Philosophy](#1-philosophy)
2. [Technology choices and rejected alternatives](#2-technology-choices-and-rejected-alternatives)
3. [Repository layout](#3-repository-layout)
4. [Data model — every table](#4-data-model--every-table)
5. [Application wiring and request lifecycle](#5-application-wiring-and-request-lifecycle)
6. [Auth and session management](#6-auth-and-session-management)
7. [Tier 1 — statement parsing pipeline](#7-tier-1--statement-parsing-pipeline)
8. [Tier 2 & 3 — categorization and the promotion loop](#8-tier-2--3--categorization-and-the-promotion-loop)
9. [Transaction views, splits, recurring detection](#9-transaction-views-splits-recurring-detection)
10. [Anomaly detection with explainability](#10-anomaly-detection-with-explainability)
11. [Text-to-SQL — "ask your finances"](#11-text-to-sql--ask-your-finances)
12. [Security hardening (Phase 8)](#12-security-hardening-phase-8)
13. [Metrics](#13-metrics)
14. [Full HTTP API surface](#14-full-http-api-surface)
15. [Frontend architecture](#15-frontend-architecture)
16. [Testing strategy](#16-testing-strategy)
17. [Infrastructure, CI, migrations, seed data](#17-infrastructure-ci-migrations-seed-data)
18. [Configuration reference](#18-configuration-reference)
19. [Known limitations and future work](#19-known-limitations-and-future-work)

---

## 1. Philosophy

Three principles drove essentially every decision:

1. **Defensible over impressive.** Where a deterministic algorithm can do
   the job, it does the job. An LLM is introduced only at the exact point
   where rules genuinely run out, it is called in batches, and its output
   is fed back into the deterministic layer so it is needed less over
   time. "94% categorized without an LLM" is a real measured number with a
   real mechanism behind it, not a marketing figure.
2. **Auditability.** Every automated decision leaves a row: how a
   transaction was categorized (`categorization_method`), which bank
   layout parsed a statement (`parse_method` + `bank_profile_id`), why an
   anomaly fired (`driving_features_json`), which query template answered a
   question (`query_template_log`), and every security-sensitive action
   (`audit_log`). Nothing is a black box.
3. **Honest failure.** A row that will not parse is logged with its raw
   text, never silently dropped. A question that maps to no query template
   is declined, not guessed at. An LLM outage degrades to "unavailable",
   not a 500.

The app was built in nine phases (0–8), each landing as a single commit,
with a review checkpoint between each.

---

## 2. Technology choices and rejected alternatives

### Backend language & framework — **FastAPI + Python 3.12**

- **Why FastAPI:** first-class async (the parsing pipeline does a lot of
  awaited DB work), Pydantic v2 request/response validation for free,
  automatic OpenAPI docs, and dependency injection that makes
  `get_current_user` / `get_db` / rate-limit guards composable.
- **Rejected — Flask:** would need Flask-RESTX/marshmallow bolted on for
  validation and docs, and async support is still second-class.
- **Rejected — Django / DRF:** the ORM and admin are a lot of surface area
  for an API-only service, and async DRF is immature. The tiered parsing
  and ML code doesn't benefit from Django's batteries.
- **Python 3.12, not 3.13/3.14:** pinned via `uv` for wheel availability
  of `scikit-learn`, `numpy`, `pdfplumber`, `pypdfium2`, `pytesseract`.
  3.14 was released too recently for reliable binary wheels across all of
  these when the project started.

### Dependency management — **uv**

- **Why:** one tool for the Python pin, the venv, the lockfile
  (`uv.lock`), and running (`uv run`). Dramatically faster than
  pip/Poetry, and `uv sync --frozen` in CI/Docker is reproducible.
- **Rejected — Poetry:** slower, historically flaky lockfile resolver,
  no Python-version management.
- **Rejected — pip + requirements.txt:** no lockfile hashing, no
  environment management, easy to drift.

### Database — **PostgreSQL 16 via SQLAlchemy 2 (async) + asyncpg**

- **Why Postgres:** `JSONB` for the several audit/decision-log tables,
  `date_trunc` for the monthly-spend rollup, real foreign keys with
  `ON DELETE` semantics the app leans on, exact `NUMERIC(14,2)` money.
- **Why SQLAlchemy 2 async:** the `Mapped[...]` typed-ORM style is
  readable and type-checked; async sessions match FastAPI's model;
  Alembic integrates directly.
- **Why asyncpg:** fastest Postgres driver for asyncio. `psycopg2-binary`
  is also installed purely so Alembic's synchronous offline paths and any
  psycopg-based tooling work.
- **Rejected — SQLite:** no `JSONB`, weaker concurrent writes, `date_trunc`
  and `NUMERIC` semantics differ; would make the test DB behave unlike
  prod.
- **Rejected — MongoDB:** the data is highly relational (users → accounts
  → statements → transactions → splits/flags). Losing joins and
  transactions to gain schema flexibility we don't want is a bad trade.
- **Rejected — an ORM like Tortoise / Piccolo:** smaller ecosystems,
  weaker migration tooling than Alembic.
- **Explicitly NOT added — pgvector / a vector store.** See
  [§11](#11-text-to-sql--ask-your-finances): transaction Q&A is a
  structured-query problem, not semantic retrieval.

### Migrations — **Alembic**

Async engine wired in `alembic/env.py`; `from app.models import *` so
`Base.metadata` is fully populated for autogenerate. Eight migrations,
one per schema-bearing phase, linear history (single head).

### Auth primitives

- **PyJWT**, not `python-jose`: `python-jose` has had unmaintained
  stretches and CVEs; PyJWT is narrower and actively maintained. HS256 is
  fine for a single-service deployment (no need for asymmetric keys with
  no third party verifying tokens).
- **bcrypt** directly, not `passlib`: `passlib` is effectively
  unmaintained and its bcrypt backend detection breaks on new bcrypt
  releases. Calling `bcrypt.hashpw` / `checkpw` directly is three lines
  and has no such problem.
- Refresh tokens are random 48-byte `secrets.token_urlsafe` values;
  **only their SHA-256 hash is stored**. Access tokens carry `sub` (user
  id) and `fid` (session family id).

### Fuzzy matching — **RapidFuzz**

Used in three places: bank-profile header similarity, merchant-name
matching, and profile-column revalidation.

- **Why:** C++-backed, MIT-licensed, fast, actively maintained, drop-in
  `fuzz.*` / `process.extractOne` API.
- **Rejected — `fuzzywuzzy` / `python-Levenshtein`:** GPL, slower,
  minimally maintained.
- Scorer choice matters and is deliberate: merchant matching uses
  `token_set_ratio` (not `WRatio`) because `WRatio`'s partial-ratio
  component false-positives on short seed patterns — e.g. `"grocery mart"`
  vs `"bart"` scores 77 under `WRatio` (a substring illusion) but 37.5
  under `token_set_ratio`, which compares token *sets*.

### PDF & OCR — **pdfplumber + pypdfium2 + pytesseract**

- **pdfplumber** for text and table extraction from digital PDFs — good
  table detection, pure-Python, no Java.
- **pypdfium2** to render scanned pages to images at ~300 DPI.
- **pytesseract** (Tesseract) for OCR on those images.
- **Rejected — `camelot` / `tabula-py`:** Java dependency (`tabula`),
  heavier install, and pdfplumber's tables are sufficient for statement
  layouts.
- **Rejected — a cloud OCR API (AWS Textract, Google Document AI):**
  sending users' bank statements to a third party for OCR is exactly the
  kind of data exposure this project is trying to avoid. Local Tesseract
  keeps the file on the box. It's weaker OCR, and the pipeline is honest
  about that: low mean confidence → `failed_needs_manual`, not garbage
  rows.
- OCR line reconstruction does **not** trust Tesseract's own block/line
  segmentation — wide inter-column gaps make it split one logical row into
  several. Instead word boxes are re-clustered by vertical position.

### Anomaly detection — **scikit-learn IsolationForest**

- **Why IsolationForest:** unsupervised (there are no anomaly labels),
  handles the small per-user sample sizes gracefully, `contamination`
  gives a direct knob for "what fraction should surface", and
  `decision_function` yields a continuous score for ranking and severity
  buckets.
- **Rejected — Local Outlier Factor:** transductive; awkward to reason
  about "refit as history grows".
- **Rejected — an autoencoder / deep model:** absurd overkill for
  30–2000 transactions per user; not explainable; a training/serving
  burden.
- **Rejected — Prophet / time-series models:** the question isn't
  "forecast next month", it's "is *this* transaction weird given the
  user's own history".
- The **feature space is hand-built and inspectable** (six features, each
  oriented so higher = more unusual). The only ML is the forest finding
  joint outliers in that space. The "which feature drove this flag"
  explanation is a **robust z-score** (median/MAD) of each feature against
  the training rows — explicitly a heuristic, not SHAP.

### LLM integration — **OpenAI-compatible API, structured output**

- **Why OpenAI-compatible (not the Anthropic SDK, despite this being
  built with Claude Code):** the `openai` Python SDK's
  `chat.completions.parse` with a Pydantic `response_format` gives
  schema-constrained output — the model *cannot* return a category or
  template name outside the allowed enum. Pointing `base_url` at any
  OpenAI-compatible endpoint (OpenAI, local llama.cpp, vLLL, etc.) works
  unchanged. The key is read from `LLM_API_KEY`, never hardcoded.
- **Rejected — raw prompt + regex/JSON parsing:** brittle; the whole
  point of structured output is eliminating the "model returned prose"
  failure mode.
- **Rejected — LangChain:** its SQL agent / output parsers are a heavy
  abstraction over what is, here, two ~20-line functions. More
  dependency surface than value.
- The LLM is used in exactly **two** places: Tier 3 categorization
  fallback (batched, one call per ~20 distinct merchants) and text-to-SQL
  template selection (never SQL generation).

### Frontend — **Next.js 16 (App Router) + TypeScript + Tailwind v4**

- **Why Next.js:** file-system routing, a sane build, first-class TS. The
  app is entirely client components (`"use client"`) talking to the
  FastAPI backend — Next is used as a well-tooled React app shell, not for
  SSR/RSC data fetching.
- **Rejected — plain Vite + React Router:** would work; Next gives routing
  + build + lint config in one place and is a more common resume signal.
- **Charts are hand-rolled inline SVG** (`ranked-bar-chart.tsx`,
  `spend-trend-chart.tsx`), not Recharts/Chart.js/D3: two simple chart
  types, no need for a ~100 KB charting dependency, full control over
  theming via CSS variables, and they render identically server- and
  client-side.
- **Tailwind v4** via `@tailwindcss/postcss` — utility styling with no
  component library.

### Rate limiting — **in-process fixed-window**

- **Why hand-rolled:** the spec calls for rate limiting with *no Redis*,
  and this is a single-process deployment. ~30 lines: a per-IP timestamp
  list per scope, pruned on each hit.
- **Rejected — `slowapi`:** pulls in `limits` and is oriented toward
  distributed backends we're explicitly not using.
- **Rejected — nginx `limit_req`:** would work in a real deployment but
  moves the logic out of the app and out of the test suite. The honest
  caveat (documented) is that behind multiple workers each worker has its
  own window; the fix at that point is a shared store.

---

## 3. Repository layout

```
finance-app/
├── README.md                 architecture summary + measured metrics
├── IMPLEMENTATION.md          this file
├── docker-compose.yml         postgres + backend + frontend
├── .github/workflows/ci.yml   lint → pytest → frontend build → compose build
├── backend/
│   ├── pyproject.toml         deps, ruff + pytest config
│   ├── Dockerfile             python:3.12-slim + tesseract-ocr
│   ├── alembic/               migrations (env.py wires the async engine)
│   ├── scripts/
│   │   ├── seed_merchant_lookup.py    starter merchant→category rules
│   │   ├── seed_demo.py               demo user + synthetic multi-bank history
│   │   └── generate_statement_fixtures.py   one-off test-fixture generator
│   └── app/
│       ├── main.py            FastAPI app, CORS, router registration
│       ├── core/              config, database, security, rate_limit
│       ├── models/            14 SQLAlchemy models
│       ├── schemas/           Pydantic request/response models
│       ├── api/               10 routers (thin — HTTP concerns only)
│       └── services/          all business logic
│           ├── parsing/       Tier 1 pipeline (16 modules)
│           ├── categorization/  Tier 2/3 + promotion + seed data
│           ├── anomaly/       features, detector, orchestration
│           └── text_to_sql/   templates, llm_selector, service
└── frontend/
    └── src/
        ├── app/               App Router pages (one dir per route)
        ├── components/        nav bar, charts, badges, modal
        └── lib/               api client, auth context, endpoints, types
```

**Layering rule:** `api/` routers are thin and only do HTTP (status codes,
`HTTPException` mapping, auth dependencies). All logic lives in
`services/`. Models never import services. Services never import routers.

---

## 4. Data model — every table

All primary keys are `UUID` (`uuid4`, app-generated). All timestamps are
`TIMESTAMP WITH TIME ZONE` with a `server_default` of `now()`. Money is
`NUMERIC(14,2)`; the canonical sign convention everywhere is **positive =
inflow/credit, negative = outflow/debit**.

Migration chain (oldest → newest):
`7ca738897a8d` users/refresh_tokens →
`15bd86c1e4ea` statement parsing tables →
`d1796c1bbe9a` merchant_lookup →
`2fcfb6b34c40` llm decision/batch logs →
`27e97f6a3b7f` accounts + transaction_splits →
`b7e2a1f4c9d3` anomaly_flags →
`c4d8e2f19a67` query_template_log →
`e5f1a9c72b84` audit_log.

### `users`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| email | VARCHAR(320) | unique, indexed |
| hashed_password | VARCHAR(255) | bcrypt |
| created_at | timestamptz | |

`refresh_tokens` relationship with `cascade="all, delete-orphan"`.

### `refresh_tokens`
One row per issued refresh token in a rotation chain.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK→users **ON DELETE CASCADE** | indexed |
| token_hash | VARCHAR(64) | **SHA-256 of the raw token**, unique, indexed |
| family_id | UUID | indexed — identifies one continuous session/device |
| revoked | BOOL | default false |
| expires_at | timestamptz | now + `REFRESH_TOKEN_EXPIRE_DAYS` |
| created_at | timestamptz | |
| user_agent | VARCHAR(512) | captured at issue time |
| ip_at_creation | VARCHAR(64) | captured at issue time |

Every rotation inserts a new row with the **same `family_id`** and flips
the previous row `revoked=true`. Presenting an already-revoked token →
the whole family is revoked (theft response).

### `accounts`
User-created, user-managed (e.g. "Chase Checking"). Explicit rather than
inferred from statement text so per-account vs consolidated views are
exact.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK→users **CASCADE** | indexed |
| display_name | VARCHAR(255) | |
| bank_name | VARCHAR(255) | nullable |
| account_type | VARCHAR(32) | `checking` / `savings` / `credit_card` / `other` |
| created_at | timestamptz | |

### `bank_profiles`
A **learned statement layout**, keyed by a fingerprint of the header text
(or a structural signature for non-tabular PDFs) — **never by bank name**.
**Global across all users** on purpose: a row stores only column-layout
and date-format metadata, never transaction data, so sharing it is what
lets the system get better per-layout for everyone.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| structure_type | VARCHAR(32) | `csv_header` / `pdf_table_header` / `pdf_text_regex` |
| header_fingerprint_hash | VARCHAR(64) | SHA-256 of normalized header text, indexed |
| header_fingerprint_normalized | TEXT | the normalized header text itself (for fuzzy compare) |
| column_map_json | JSON | `{role: header_cell_text}` for grid layouts; `{date_pattern, day_first, amounts_per_line}` for text layouts |
| date_format | VARCHAR(64) | e.g. `%d/%m/%Y`, or a pattern name for text PDFs |
| amount_sign_convention | VARCHAR(64) | one of the resolved conventions — see §7.5 |
| regex_pattern | TEXT | nullable, for text-PDF layouts |
| sample_lines_json | JSON | nullable, a few raw header/data lines for debugging |
| learned_at | timestamptz | |
| last_used_at | timestamptz | nullable |
| times_used | INT | default 1 |
| times_rejected | INT | default 0 — incremented when a candidate profile fails revalidation |

### `statements`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK→users **CASCADE** | indexed |
| account_id | UUID FK→accounts **ON DELETE SET NULL** | indexed, nullable |
| bank_hint | VARCHAR(255) | free-text hint supplied at upload, nullable |
| bank_profile_id | UUID FK→bank_profiles **SET NULL** | which layout parsed it |
| original_filename | VARCHAR(512) | |
| file_path | VARCHAR(1024) | on-disk path under `UPLOAD_STORAGE_DIR/<user_id>/` |
| file_type | VARCHAR(16) | `csv` / `pdf` / `image` |
| detected_structure | VARCHAR(32) | `clean_csv` / `pdf_table` / `pdf_text_no_table` / `pdf_scan_ocr` / `image_scan_ocr` |
| parse_status | VARCHAR(32) | `pending` / `parsed_clean` / `parsed_with_warnings` / `failed_needs_manual` |
| parse_method | VARCHAR(32) | `cold_detection` / `profile_reuse` |
| bank_profile_match_score | FLOAT | nullable, 0–100 (100 = exact hash hit) |
| row_count_total / _parsed / _failed | INT | |
| error_message | TEXT | nullable |
| uploaded_at / updated_at | timestamptz | `updated_at` has `onupdate=now()` |

### `transactions`
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| statement_id | UUID FK→statements **CASCADE** | indexed |
| user_id | UUID FK→users **CASCADE** | indexed (denormalized so user-scoped queries skip a join) |
| account_id | UUID FK→accounts **SET NULL** | indexed, nullable (denormalized from statement) |
| raw_merchant | TEXT | exactly as parsed |
| normalized_merchant | VARCHAR(255) | nullable — cleaned string or a matched canonical name |
| category | VARCHAR(64) | nullable — one of the 14 categories; **cleared to NULL when the transaction is split** |
| categorization_method | VARCHAR(32) | nullable — `rule_exact` / `rule_fuzzy` / `llm` / `manual_user_correction`; **NULL = genuinely unresolved** |
| confidence | NUMERIC(4,3) | nullable, 0–1 |
| amount | NUMERIC(14,2) | signed, canonical convention |
| date | DATE | |
| running_balance | NUMERIC(14,2) | nullable, when the statement had a balance column |
| raw_line_text | TEXT | nullable — the source line, kept for debugging |
| row_index | INT | nullable — position in the source file |
| created_at | timestamptz | |

### `transaction_splits`
One category allocation of a split transaction. Split amounts must sum
**exactly** to the parent's `amount` (validated at write time in the
service, not by a DB constraint). When a transaction has any splits its
own `category` is NULL and spending views use these rows instead.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| transaction_id | UUID FK→transactions **CASCADE** | indexed |
| category | VARCHAR(64) | |
| amount | NUMERIC(14,2) | signed |
| created_at | timestamptz | |

### `parse_failures`
Every row (or header/whole-statement issue) that failed to parse, with
its raw text. Never a silent drop.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| statement_id | UUID FK→statements **CASCADE** | indexed |
| row_index | INT | nullable (NULL = statement-level failure) |
| raw_line_text | TEXT | |
| reason_code | VARCHAR(64) | e.g. `unparseable_date`, `ocr_low_confidence`, `ambiguous_sign_convention` |
| reason | TEXT | human-readable |
| created_at | timestamptz | |

### `merchant_lookup`
`raw_pattern → normalized_name/category`, matched exactly or fuzzily.
**Global** (like bank profiles).
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| raw_pattern | VARCHAR(255) | **cleaned** merchant key, unique, indexed |
| normalized_name | VARCHAR(255) | canonical display name |
| category | VARCHAR(64) | |
| match_type | VARCHAR(32) | how *this row* came to exist: `seed` / `user_correction` / `llm_promotion` |
| promoted_from_llm | BOOL | default false |
| created_at | timestamptz | |

### `llm_batch_calls`
One row per Tier 3 API call (a batch of distinct merchants). Cost is
tracked here, at the call level, so summing can't double-count.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| model_used | VARCHAR(128) | |
| merchant_count | INT | distinct merchants in the batch |
| prompt_tokens / completion_tokens | INT | from the API `usage` |
| estimated_cost_usd | FLOAT | `tokens/1000 × configured per-1k rates` |
| created_at | timestamptz | |

### `llm_decision_log`
One row per **distinct merchant** the LLM categorized (not per
transaction). This is the growing labeled dataset the promotion job mines.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| raw_merchant | TEXT | a representative raw string |
| cleaned_merchant | VARCHAR(255) | the cleaned key, indexed |
| llm_category | VARCHAR(64) | |
| confidence | FLOAT | |
| model_used | VARCHAR(128) | |
| batch_id | UUID FK→llm_batch_calls **CASCADE** | |
| promoted | BOOL | default false — flips true once mined into `merchant_lookup` |
| created_at | timestamptz | |

### `anomaly_flags`
One row per transaction the per-user IsolationForest flagged.
`UniqueConstraint(transaction_id)`.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| transaction_id | UUID FK→transactions **CASCADE** | indexed, unique |
| user_id | UUID FK→users **CASCADE** | indexed |
| severity | VARCHAR(16) | `low` / `medium` / `high` (heuristic buckets on `score`) |
| score | FLOAT | raw `decision_function` output — more negative = more anomalous |
| driving_features_json | JSONB | ranked `[{feature, explanation, z_score, value}]` — the whole point |
| dismissed | BOOL | default false |
| dismissal_reason | VARCHAR(255) | nullable |
| dismissed_at | timestamptz | nullable |
| created_at | timestamptz | |

A dismissed flag is **never re-created** on the next refit and never
counted as new — the dismissal is training feedback (see §10).

### `query_template_log`
One row per "ask your finances" question, answered or not.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK→users **CASCADE** | indexed |
| question_text | TEXT | |
| matched_template | VARCHAR(64) | nullable — **NULL ⇔ the question was declined** |
| confidence | FLOAT | nullable — the model's self-reported selection confidence |
| params_json | JSONB | the validated params that ran (or `{}` on a decline) |
| declined | BOOL | default false |
| result_summary | TEXT | the plain-language answer or the decline reason |
| created_at | timestamptz | |

### `audit_log`
Append-only security trail.
| column | type | notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK→users **ON DELETE SET NULL** | nullable, indexed (a failed login has no user) |
| action | VARCHAR(64) | indexed — see the action vocabulary in §12 |
| target_type | VARCHAR(32) | nullable — `statement` / `email` / `session_family` |
| target_id | VARCHAR(128) | nullable — **text, not UUID**, because a target is sometimes an email |
| ip_address | VARCHAR(64) | nullable |
| user_agent | VARCHAR(512) | nullable, truncated |
| detail_json | JSONB | default `{}` — e.g. `{filename, parse_status}` on an upload |
| created_at | timestamptz | indexed |

---

## 5. Application wiring and request lifecycle

- **`app/main.py`** creates the `FastAPI` app, adds `CORSMiddleware`
  restricted to `FRONTEND_ORIGIN` with credentials, and registers ten
  routers: health, auth, statements, transactions, accounts, admin,
  anomalies, ask.
- **`app/core/config.py`** — a single `pydantic_settings.BaseSettings`
  subclass, `@lru_cache`d via `get_settings()`. Env vars (or `.env`)
  override defaults; unknown keys ignored. Every tunable in the app is a
  field here (full list in §18).
- **`app/core/database.py`** — one async engine + `async_sessionmaker`
  (`expire_on_commit=False`). `get_db()` is an async-generator dependency
  yielding one session per request.
- **`app/api/deps.py`** — `HTTPBearer(auto_error=False)` →
  `get_token_payload` (decodes/validates the JWT, 401 on any failure) →
  `get_current_user` (loads the `User` row) and `get_current_family_id`
  (pulls `fid` for "is this the current session" checks).
- Every business endpoint depends on `get_current_user` + `get_db`. Auth
  and upload endpoints additionally depend on a rate-limit guard.

---

## 6. Auth and session management

**Files:** `app/services/auth_service.py`, `app/core/security.py`,
`app/api/auth.py`, `app/models/refresh_token.py`.

### Registration & login
- `POST /auth/register` — bcrypt-hash the password, insert the user. 409
  on duplicate email. Rate-limited (`auth` scope).
- `POST /auth/login` — verify with `bcrypt.checkpw`. On success: create a
  new `family_id`, issue a token pair, write an `auth.login` audit row.
  On failure: write an `auth.login_failed` audit row (with the attempted
  email as `target_id`, `user_id` NULL) and 401. Rate-limited.

### Token pair
- **Access token:** HS256 JWT, `{sub, fid, type: "access", iat, exp}`,
  `exp = now + ACCESS_TOKEN_EXPIRE_MINUTES` (default 15).
- **Refresh token:** 48 random bytes, urlsafe. Only `sha256(raw)` is
  stored in `refresh_tokens.token_hash`. `expires_at = now +
  REFRESH_TOKEN_EXPIRE_DAYS` (default 30).

### Rotation + reuse detection — `POST /auth/refresh`
1. Hash the presented token, look up the row.
2. **No row** → 401 `InvalidRefreshTokenError`.
3. **Row exists but `revoked=true`** → this token was already rotated out.
   Treat as theft/replay: revoke the **entire family**
   (`UPDATE refresh_tokens SET revoked=true WHERE family_id=…`), write an
   `auth.refresh_reuse_detected` audit row, 401 with a "reuse detected"
   message.
4. **Row expired** → 401.
5. **Valid** → mark this row `revoked=true`, issue a new pair with the
   **same `family_id`**.

`refreshTokens()` on the frontend serializes concurrent 401-driven
refreshes through a single in-flight promise, so a burst of parallel
requests can't each fire their own rotation and trip reuse detection.

### Sessions UI
- `GET /auth/sessions` — active (`revoked=false`) families for the user,
  each with `user_agent`, `ip_at_creation`, `created_at`, `expires_at`,
  and `is_current` (matches the caller's `fid`).
- `DELETE /auth/sessions/{family_id}` — ownership-checked, revokes that
  family, writes `auth.session_revoked`. 404 if the family isn't the
  caller's.
- `POST /auth/logout` — revokes the family of the presented refresh token.
- `GET /auth/activity` — the caller's own `audit_log` rows, newest first
  (limit clamped 1–200).

---

## 7. Tier 1 — statement parsing pipeline

**Entry point:** `statement_service.upload_and_parse_statement` →
`parsing/pipeline.parse_statement`. The pipeline **never raises** to the
API; any unresolvable structure becomes a `failed_needs_manual` statement
with a logged `ParseFailure`.

### 7.1 Structure detection — `parsing/structure_sniffer.py`
The upload endpoint accepts **any file type** — there is no extension
allowlist. The sniffer decides how to parse it from the content:
- A raster image (by magic bytes — PNG/JPEG/GIF/BMP/TIFF/WEBP — or image
  extension) → `image_scan_ocr`, `file_type = image`. A phone photo of a
  paper statement lands here.
- A PDF (by extension or `%PDF` magic bytes) → sample the first
  `PDF_STRUCTURE_DETECTION_PAGE_SAMPLE` pages with pdfplumber: any real
  table (≥2 rows × ≥2 cols) → `pdf_table`; else any substantial text →
  `pdf_text_no_table`; else → `pdf_scan_ocr`.
- Everything else — CSV, TSV, plain text, or an unrecognized upload →
  `clean_csv`, fed to the delimited-grid parser. Non-tabular bytes fail
  honestly (a logged `ParseFailure` + `failed_needs_manual`), never a crash.

### 7.2 Profile lookup & the reuse/cold decision — `parsing/profile_service.py`
`structure_type` maps `clean_csv → csv_header`,
`pdf_table → pdf_table_header`, and
`pdf_text_no_table`/`pdf_scan_ocr`/`image_scan_ocr → pdf_text_regex`.

**Grid layouts (CSV, PDF-table)** — reuse is a genuine shortcut:
1. Read the grid. Scan the first `MAX_HEADER_SCAN_ROWS` rows; for each,
   build a normalized fingerprint string and look for a candidate profile
   (`parsing/fingerprint.py`): **exact SHA-256 hash hit** (score 100), else
   **`fuzz.WRatio`** against up to 200 same-`structure_type` profiles,
   accepting the best if ≥ `BANK_PROFILE_FUZZY_MATCH_THRESHOLD` (default
   90).
2. **Revalidate the candidate against this file** before trusting it:
   re-resolve column roles from the stored `column_map_json` by fuzzy-
   matching stored header text to the actual header cells (≥
   `PROFILE_REVALIDATION_MATCH_THRESHOLD`), require all `REQUIRED_ROLES`
   plus either `amount` or (`debit` and `credit`), and confirm ≥ 80 % of a
   date-column sample still parse under the stored `date_format`.
3. Pass → parse with the known roles (`grid_parser.parse_rows_with_known_
   roles`), `parse_method = profile_reuse`, bump `times_used`.
4. Fail → bump the candidate's `times_rejected`, fall through to cold.
5. **Cold:** full `parse_grid` (header detection + `column_classifier` +
   `sign_convention`), then **upsert** the profile keyed by the header
   hash, `parse_method = cold_detection`.

**Text/OCR layouts** — the regex parser is cheap, so the file is parsed
first regardless; the outcome's structural signature is then compared to
saved profiles to *classify* it reuse-vs-cold. The metric stays honest;
it just isn't a performance shortcut for this structure type.

### 7.3 Header detection & column classification — `parsing/column_classifier.py`
- Normalize header cells; for each, fuzzy-match against `ROLE_SYNONYMS`
  (date / description / amount / debit / credit / balance /
  sign_indicator) with `fuzz.WRatio` ≥ `HEADER_SYNONYM_MATCH_THRESHOLD`.
- Assign highest-scoring (role, column) pairs greedily, one column per
  role.
- **Content sanity check:** for each assigned role with a dtype
  expectation (date-like / numeric-like), sample the column's values; if
  < 30 % match the expected shape, **unassign** the role and warn ("header
  said `amount` but the values aren't numeric").
- Require `REQUIRED_ROLES` + (`amount` or `debit`+`credit`) or the layout
  is unresolvable.

### 7.4 Date handling
Grid parsers infer and store a concrete `strftime` format. Text PDFs use
ordered regex patterns (`iso`, `day_month_name`, `month_name_day`,
`slash_ambiguous`, `dash_ambiguous`); the **dominant** pattern in the file
wins, non-conforming lines become `ParseFailure`s, and day-vs-month order
for ambiguous numeric dates is resolved **once per statement** from a
sample (a value > 12 in the second slot ⇒ day-first, in the first slot ⇒
month-first, otherwise default day-first).

### 7.5 Sign-convention resolution — `parsing/sign_convention.py`
Resolves a canonical **signed** amount per row and records which
convention was used (persisted on the profile so it's reused, not
re-derived):
| convention | when | rule |
|---|---|---|
| `separate_debit_credit_columns` | both `debit` & `credit` roles | `credit − |debit|` |
| `debit_negative_single_column` | single `amount` col, some values already negative | use as-is |
| `single_column_sign_indicator` | a `sign_indicator` role (DR/CR, etc.) | apply sign from the indicator token; unknown ⇒ assume debit + warn |
| `single_column_balance_inferred` | a `balance` column present | order rows by date, compare successive balance deltas to the magnitude (± 0.02 tolerance); unresolved rows ⇒ assume debit + warn |
| `single_column_assume_debit` | none of the above | assume all-debit, emit a statement-level `ambiguous_sign_convention` `ParseFailure` |

### 7.6 CSV specifics — `parsing/csv_parser.py`
Stdlib `csv`, **not pandas**: real statement exports are frequently ragged
(banner rows with fewer fields than the data rows), and pandas rejects
ragged input unless told the exact column count up front — which isn't
known until header detection runs. `csv.reader` tolerates raggedness
natively. Decoded as `utf-8-sig` to strip BOMs.

### 7.7 OCR specifics — `parsing/ocr_parser.py`
Render each page at ~300 DPI (`pypdfium2`), OCR with `pytesseract`,
**re-cluster word boxes by vertical position** (don't trust Tesseract's
line segmentation across wide column gaps), feed reconstructed lines to
the text-PDF parser. `parse_image_ocr` reuses the same word-box
reconstruction and post-processing for a bare uploaded image (`Pillow`
opens it; anything undecodable → `no_text_extracted`). A missing Tesseract
binary or mean confidence below `OCR_MIN_CONFIDENCE` (default 40) →
`UnresolvableStructureError` → `failed_needs_manual` (never garbage rows).
Tesseract is installed in the Docker image and CI; its absence degrades
gracefully everywhere else.

### 7.8 Persisting the outcome — `parsing/pipeline.py`
Writes `Transaction` rows and `ParseFailure` rows, sets
`row_count_total/parsed/failed`, and sets `parse_status`:
`parsed_clean` (no failures/warnings) / `parsed_with_warnings` (some
row failures or sign warnings) / `failed_needs_manual` (zero rows
parsed). Then the pipeline returns and `statement_service` runs Tier 2,
then Tier 3, then a best-effort anomaly refit, then writes the
`statement.upload` audit row.

---

## 8. Tier 2 & 3 — categorization and the promotion loop

**Files:** `app/services/categorization/` — `merchant_cleaner.py`,
`matcher.py`, `service.py` (Tier 2), `llm_client.py` + `tier3.py` (Tier
3), `promotion.py`, `seed.py` + `seed_data.py`, `constants.py`.

### 8.1 Merchant cleaning — `merchant_cleaner.py`
Deliberately boring regex-only cleanup that produces a lowercase matching
key. **Most of the "AI-sounding merchant normalization problem" is
actually solved here**, before any matching runs:
- strip leading payment-rail boilerplate (`POS`, `UPI`, `NEFT`, `ACH`,
  `CARD PURCHASE`, …)
- strip UPI handles (`@okhdfcbank`), long reference/auth codes (`#?\d{6,}`),
  standalone long digit runs
- collapse separators/punctuation/whitespace
- drop a trailing US state code (`… AUSTIN TX` → `… austin`)

Full city removal is out of scope (would need a gazetteer) — fuzzy
matching picks up that slack.

### 8.2 The 14 categories
`groceries, dining, food_delivery, transit, utilities, subscriptions,
entertainment, shopping, travel, health, income, transfers, fees, other`.
Defined once in `categorization/constants.py` as `CATEGORIES` and a
`CategoryLiteral` typing `Literal`, reused by every schema and the LLM
`response_format` so drift is impossible.

### 8.3 Tier 1/2 matching — `matcher.py`, `service.py`
`categorize_statement_transactions` runs right after parsing, over every
transaction on the statement:
- Build a `MerchantMatcher` **once** from a single `SELECT * FROM
  merchant_lookup` (not re-queried per row).
- **Exact:** O(1) dict lookup on the cleaned string → `rule_exact`,
  confidence 1.0.
- **Fuzzy:** `process.extractOne(cleaned, scorer=fuzz.token_set_ratio)`;
  must clear `FUZZY_MATCH_SCORE_FLOOR` (60) **and**
  `CATEGORIZATION_CONFIDENCE_THRESHOLD` (0.75) → `rule_fuzzy`.
- **No match:** `categorization_method` stays NULL —
  `normalized_merchant` is set to the cleaned string, and this is exactly
  the set Tier 3 picks up.

### 8.4 Tier 3 — batched LLM fallback — `tier3.py`, `llm_client.py`
- No-ops immediately if `LLM_API_KEY` is unset.
- Group the statement's still-unresolved transactions by cleaned merchant
  string. **Several transactions sharing a merchant cost one decision.**
- For each chunk of ≤ `LLM_MAX_BATCH_SIZE` (20) distinct merchants: one
  `client.chat.completions.parse` call with
  `response_format=BatchCategorizationResponse` (so category is a
  constrained enum). A failed chunk is skipped, not fatal — those
  transactions simply stay unresolved.
- Per call: write an `llm_batch_calls` row with token counts and
  `estimated_cost_usd`. Per distinct merchant: apply the category to all
  its transactions (`categorization_method = llm`) and write an
  `llm_decision_log` row.
- After the batches: `db.commit()` then `run_promotion_job(db)` inline.

### 8.5 The promotion job — `promotion.py`
`GROUP BY cleaned_merchant` over **un-promoted** `llm_decision_log` rows,
`HAVING count() ≥ LLM_PROMOTION_MIN_OCCURRENCES` (default 3) **and**
exactly one distinct `llm_category` for that merchant. Each qualifying
merchant is upserted into `merchant_lookup` (`match_type =
llm_promotion`, `promoted_from_llm = true`) and its decision rows get
`promoted = true`. This is the actual mechanism by which the Tier 3 rate
falls over time. Also runnable on demand via
`POST /admin/promotion-job/run`.

### 8.6 Manual correction feedback — `service.recategorize_transaction`
`PATCH /transactions/{id}/category` fixes the transaction
(`manual_user_correction`, confidence 1.0) **and** upserts a
`merchant_lookup` row (`match_type = user_correction`) so future
transactions from that merchant resolve at Tier 2 directly — the same
closed loop as promotion.

### 8.7 Seeding — `seed.py` / `seed_data.py`
~60 well-known merchant→category rules (`match_type = seed`), idempotent,
run via `scripts/seed_merchant_lookup.py`. This is the starting
deterministic knowledge; the promotion job and manual corrections grow it.

---

## 9. Transaction views, splits, recurring detection

**Files:** `app/services/transaction_service.py`,
`app/services/recurring_service.py`, `app/api/transactions.py`,
`app/schemas/views.py`.

### Unified transaction list — `GET /transactions`
Cross-statement, cross-account, newest first, paginated
(`page`, `page_size` ≤ 200). Filters: `account_id`, `category`,
`start_date`, `end_date`, `search` (ILIKE on `raw_merchant`). The
response marks `is_split` per row (computed from a single
`transaction_splits` lookup, not a column).

### Splits
`POST /transactions/{id}/split` with ≥ 2 `{category, amount}` allocations
that **sum exactly to the parent amount** (same sign). On success the
parent's `category`/`method`/`confidence` are cleared. `DELETE …/split`
removes the allocations. Spending queries then attribute split
transactions to their allocation categories, not the (now-NULL) parent
category.

### Spending views (outflows only — `amount < 0`)
- **By category** (`/spending/by-category`): sums non-split transactions
  grouped by `category` **plus** split-allocation sums grouped by split
  `category`, magnitudes reported positive. `uncategorized` bucket for
  NULL.
- **Trend** (`/spending/trend?months=N`): `date_trunc('month', date)`
  rollup over the trailing N months, **zero-filled** so charts have no
  gaps.
- **Top merchants** (`/spending/top-merchants`): `GROUP BY
  normalized_merchant ORDER BY sum(amount)` (most negative = most spent),
  using each transaction's full amount (splitting allocates category, not
  merchant).

### Recurring detection — `recurring_service.py`
An explainable periodicity heuristic, **not** an ML model:
1. Group by `normalized_merchant`.
2. Within a merchant, **greedy 1-D cluster by amount** (new cluster when
   the gap to the previous amount exceeds `max(5.00, 10 %)`) — handles
   both fixed subscriptions and slightly-varying utility bills.
3. A cluster with ≥ 3 occurrences whose inter-occurrence gaps are regular
   (population stdev ≤ `max(3 days, 25 % of mean gap)`) and whose mean gap
   is within 25 % of a known bucket (weekly / biweekly / monthly /
   quarterly / yearly) is a recurring group. `next_expected_date =
   last_date + round(mean_gap)`.

---

## 10. Anomaly detection with explainability

**Files:** `app/services/anomaly/features.py`, `detector.py`,
`service.py`; `app/models/anomaly_flag.py`; `app/api/anomalies.py`.

### 10.1 Feature space — `features.py`
Only **outflows** are scored (an unusual *deposit* isn't the signal;
letting salary credits into the amount distribution would swamp
everything). Six features, matrix order, **each oriented so higher = more
unusual**:
| feature | definition |
|---|---|
| `amount_ratio_in_category` | `abs(amount) / median(abs amounts in that category)` (median floored at 1.0) |
| `amount_magnitude_log` | `log1p(abs amount) / log1p(user's largest outflow)` — currency-size-agnostic 0–1 |
| `category_rarity` | `1 − (count in this category / total)` |
| `merchant_novelty` | `1.0` if this is the first chronological transaction with this merchant, else `0.0` (binary) |
| `day_of_week_rarity` | `1 − (count on this weekday / total)` |
| `time_of_month_rarity` | `1 − (count in this third of the month / total)` |

The single "higher = more unusual" convention is what lets the explainer
treat "features far above this user's normal" as "features that drove the
flag" with no per-feature direction handling.

### 10.2 The model — `detector.py`
- If the user has < `ANOMALY_MIN_TRANSACTIONS` (30) outflows →
  `(results=[], model_trained=False)`. The caller treats that as "no
  opinion", **not** "nothing is wrong".
- `IsolationForest(n_estimators=200, contamination=ANOMALY_CONTAMINATION
  (0.05), random_state=42)`, `fit_predict` + `decision_function` on the
  feature matrix.
- **Explainability** (`_explain`): for each non-binary feature, a **robust
  z-score** `(value − median) / (1.4826 × MAD)` (falling back to
  std-based z when MAD ≈ 0) against the training column; features with
  `z ≥ ANOMALY_EXPLAIN_Z_THRESHOLD` (2.0) become drivers, ranked by z.
  Binary `merchant_novelty` is a driver iff it's set and < 35 % of rows
  have it set. If the forest flagged a joint outlier where no single
  feature clears the bar, one honest "unusual combination" driver is
  emitted. Each driver gets a templated sentence
  (`explanation_for`), e.g. *"Amount $1,180 is 18.9x your typical
  groceries spend ($62)"*.
- **Severity** is a presentation bucket on `score`: ≤ −0.12 high, ≤ −0.04
  medium, else low.

### 10.3 Orchestration & the dismissal feedback loop — `service.py`
`run_anomaly_detection` (triggered by `POST /anomalies/detect` and
best-effort after every upload):
1. Load the user's transactions and their **suppressed signatures** — the
   `(merchant.lower(), category)` pairs of every flag they've ever
   dismissed.
2. `detector.detect(..., suppressed_signatures=…)`. A row whose signature
   is suppressed is kept **only if a *hard* driver** (an amount feature)
   still fires — "I know I shop there" shouldn't excuse a 20× charge, but
   it does silence a novel-merchant/rare-category flag.
3. Reconcile the flag table: new anomalies → insert; still-anomalous →
   update severity/score/drivers; **dismissed flags are never touched or
   recreated**; previously-flagged-and-not-dismissed rows the refit no
   longer considers anomalous are **deleted** (the user's normal moved).
4. `GET /anomalies` returns the feed most-anomalous first;
   `POST /anomalies/{id}/dismiss` sets `dismissed`, `dismissal_reason`,
   `dismissed_at`; `GET /anomalies/stats` returns counts +
   `dismissal_rate`.

Tested against a synthetic history with two injected anomalies (a ~20×
grocery charge, a novel travel merchant): the suite asserts **recall =
1.0** on the injected set with a 0.4 precision floor (the "normal" rows
are unlabelled and legitimately contain borderline cases, so demanding
perfect precision against synthetic data would be dishonest).

---

## 11. Text-to-SQL — "ask your finances"

**Files:** `app/services/text_to_sql/templates.py`, `llm_selector.py`,
`service.py`; `app/api/ask.py`; `app/models/query_template_log.py`.

### 11.1 Why templates, not generated SQL, not RAG
Transaction Q&A is a **structured-data** problem. Embedding numeric rows
and retrieving by similarity discards the precision a real aggregate
query keeps, so there is **no vector store and no pgvector**. Letting the
LLM emit SQL creates an injection surface and a cross-user-leak risk and
makes the query surface unauditable. Instead:

### 11.2 The template registry — `templates.py`
Six reviewed, parameterized templates, each a `QueryTemplate(name,
description, params_model, run)`:
| template | params model | returns |
|---|---|---|
| `total_spend_in_period` | `PeriodParams` (start, end, optional category) | one number |
| `spend_by_category_in_period` | `PeriodParams` | rows + bar chart |
| `top_merchants_in_period` | `TopNPeriodParams` (+ limit 1–50) | rows + bar chart |
| `compare_spend_between_periods` | `ComparePeriodsParams` (two ranges) | A vs B + delta + % |
| `monthly_spend_trend` | `TrendParams` (months 1–24, optional category) | rows + line chart |
| `largest_transactions` | `TopNPeriodParams` | rows |

Every `run(db, user_id, params)` builds its query with
`Transaction.user_id == user_id` **as a literal filter in the builder** —
never from anything the LLM produced. Param models are Pydantic with
`model_config = ConfigDict(extra="ignore")`, so a completion that stuffs
a `user_id` (or anything else) into its params has it **silently
dropped**. Date-order (`end ≥ start`) is validated by `model_validator`.
Spend = `amount < 0`, reported as positive magnitudes.

### 11.3 The LLM's only job — `llm_selector.py`
`select_template(question)` calls `chat.completions.parse` with
`response_format=TemplateSelection` where
`template_name: Literal[<the six names>, "none"]`. The model **cannot**
return a name outside that set. It also returns `confidence: float` and a
flat `SelectionParams` object (union of every template's params, all
optional, `extra="ignore"`). A module-level `assert` keeps the `Literal`
in sync with the registry. The system prompt lists the templates and
their descriptions, fixes ISO dates resolved against *today*, and lists
the allowed category values.

### 11.4 Orchestration — `service.answer_question`
1. No `LLM_API_KEY` → decline "not configured" (logged).
2. `select_template` raises → decline "temporarily unavailable" (logged).
3. `template_name == "none"` or `confidence <
   TEXT_TO_SQL_MIN_CONFIDENCE` (0.6) → decline "no supported query fits"
   (logged, `matched_template` NULL).
4. Re-validate `selection.params` against the **chosen template's own**
   Pydantic model. `ValidationError` → decline "matched X but couldn't
   fill it in — <first error>" (logged, `matched_template` NULL).
5. Run the template (user-scoped in the builder). Log the answered row
   with the template, confidence, validated params, and summary.
6. Return `{answered, matched_template, confidence, summary, columns,
   rows, chart}`.

**Every** outcome writes a `query_template_log` row, which is where the
honest template-match rate comes from. Two tests specifically prove that
an adversarial `SelectionParams` carrying another user's id + a
2000–2100 date range still returns only the caller's data (once through
the endpoint, once directly at the param-model layer).

---

## 12. Security hardening (Phase 8)

### 12.1 Audit log — `app/services/audit_service.py`
`record(db, action, *, user_id, target_type, target_id, request, detail,
commit)` stages an `audit_log` row; `commit=True` for standalone events
that have no other write to piggyback on. IP and (truncated) user-agent
come from the `Request`. Action vocabulary:
`auth.login`, `auth.login_failed`, `auth.refresh_reuse_detected`,
`auth.session_revoked`, `statement.upload`, `statement.delete`,
`statement.download`, `transactions.export` (reserved).
Read per-user at `GET /auth/activity`.

### 12.2 Signed download URLs — `app/api/statements.py`, `core/security.py`
Uploaded files are **never served from a static path**.
- `POST /statements/{id}/download-url` — ownership-checked, mints a JWT
  `{sub: owner_id, sid: statement_id, type: "download", exp: now +
  DOWNLOAD_URL_TTL_SECONDS (300)}` signed with the same HS256 secret but
  a distinct `type` (so it can't be swapped for an access token). Returns
  `{url: "/statements/{id}/file?token=…", expires_in_seconds}`.
- `GET /statements/{id}/file?token=…` — **no bearer**; the token is the
  auth (so a plain browser navigation works). Verifies signature +
  expiry + `type == "download"` + `sid` matches the path id, then loads
  the statement scoped to the token's `sub`, streams it via
  `FileResponse`, and writes a `statement.download` audit row. Any
  failure → 403 (bad/expired/tampered) or 404 (file gone).

Tests cover: owner round-trip, non-owner 404, tampered signature 403,
expired token 403, a token for statement A rejected on statement B's path
403.

### 12.3 Statement delete — `statement_service.delete_statement`
`DELETE /statements/{id}` — ownership-checked, `DELETE FROM statements`
(cascades to transactions → splits/anomaly-flags, and parse_failures),
unlinks the on-disk file **only if the stored path resolves inside
`UPLOAD_STORAGE_DIR`** (guards a corrupt row from becoming an arbitrary
unlink), writes `statement.delete`.

### 12.4 Rate limiting — `app/core/rate_limit.py`
`FixedWindowLimiter`: `dict[str, list[float]]` of monotonic timestamps
per `"{scope}:{client_ip}"`, pruned to the window on each hit, reject
when the list is already at the max. Two ready-made dependencies:
`auth_rate_limit` (10 / 60 s) on `login`/`register`/`refresh`,
`upload_rate_limit` (20 / 60 s) on `upload`. A 429 carries `Retry-After`.
Gated by `RATE_LIMIT_ENABLED`; an autouse test fixture disables it for
the suite, and `test_rate_limit.py` re-enables it to prove the window
bites. **Caveat:** per-process — behind multiple workers each holds its
own window; a shared store (Redis) is the scale-out fix.

### 12.5 What is deliberately *not* done
- Uploaded blobs are stored **plaintext on local disk**. Access is
  controlled (signed URLs, ownership, audit) but the bytes aren't
  encrypted at rest and aren't on object storage. Both are noted as the
  next hardening step; the spec allowed "signed expiring URLs" as the
  minimum bar.
- No admin RBAC — `/admin/*` is behind ordinary auth. The data there is
  system-wide but not per-user-sensitive.

---

## 13. Metrics

`app/services/metrics_service.compute_resume_metrics` →
`GET /admin/metrics` → the **Metrics** page. Computed live:
- categorization method breakdown, `% deterministic` vs `% via LLM` (of
  categorized rows)
- `% of statements parsed via a learned profile`, distinct profile count,
  total statements processed
- LLM batch-call count, merchants categorized, estimated cost
- text-to-SQL question count, answered count, **match rate**

Anomaly precision/recall isn't in this endpoint — it comes from
`test_anomaly_detection.py` against the injected-anomaly fixture (recall
1.0, precision floor 0.4).

---

## 14. Full HTTP API surface

| Method & path | Auth | Purpose |
|---|---|---|
| `GET /health` | – | liveness |
| `POST /auth/register` | – (rate-limited) | create user |
| `POST /auth/login` | – (rate-limited) | issue token pair; audits success/failure |
| `POST /auth/refresh` | – (rate-limited) | rotate refresh token; reuse detection |
| `POST /auth/logout` | – | revoke the token's family |
| `GET /auth/me` | bearer | current user |
| `GET /auth/sessions` | bearer | active sessions, `is_current` flagged |
| `DELETE /auth/sessions/{family_id}` | bearer | revoke a session; audited |
| `GET /auth/activity` | bearer | own audit-log rows |
| `POST /statements/upload` | bearer (rate-limited) | upload + full pipeline; audited |
| `GET /statements` | bearer | list own statements |
| `GET /statements/stats` | bearer | parse-method / structure / status rollups |
| `GET /statements/{id}` | bearer | one statement |
| `DELETE /statements/{id}` | bearer | delete + file unlink; audited |
| `POST /statements/{id}/download-url` | bearer | mint a signed URL |
| `GET /statements/{id}/file?token=` | signed token | stream the file; audited |
| `GET /statements/{id}/transactions` | bearer | transactions for a statement |
| `GET /statements/{id}/parse-failures` | bearer | logged parse failures |
| `GET /transactions` | bearer | unified paginated list + filters |
| `GET /transactions/stats` | bearer | categorization-method stats |
| `GET /transactions/recurring` | bearer | recurring groups |
| `GET /transactions/spending/by-category` | bearer | category breakdown |
| `GET /transactions/spending/trend?months=` | bearer | zero-filled monthly trend |
| `GET /transactions/spending/top-merchants` | bearer | ranked by spend |
| `PATCH /transactions/{id}/category` | bearer | manual recategorize (+ lookup feedback) |
| `GET /transactions/{id}/splits` | bearer | split allocations |
| `POST /transactions/{id}/split` | bearer | create splits (must sum to parent) |
| `DELETE /transactions/{id}/split` | bearer | remove splits |
| `POST /accounts` / `GET /accounts` | bearer | create / list accounts |
| `GET /anomalies` | bearer | flag feed, most-anomalous first |
| `POST /anomalies/detect` | bearer | refit + reconcile flags |
| `GET /anomalies/stats` | bearer | counts + dismissal rate |
| `POST /anomalies/{id}/dismiss` | bearer | dismiss (feeds next refit) |
| `POST /ask` | bearer | NL question → template answer or honest decline |
| `GET /ask/history` | bearer | recent questions (own) |
| `GET /admin/llm-stats` | bearer | LLM usage/cost totals |
| `GET /admin/metrics` | bearer | resume-metrics bundle |
| `POST /admin/promotion-job/run` | bearer | run the promotion job on demand |

---

## 15. Frontend architecture

**Stack:** Next.js 16 App Router, all client components, TypeScript,
Tailwind v4. `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`).

- **`lib/api.ts`** — `apiRequest<T>()` wrapper: injects the bearer,
  builds query strings, and on a 401 runs a **single shared in-flight
  refresh** (`refreshPromise`) then retries once. Access + refresh tokens
  in `localStorage`. `ApiError` carries status + parsed `detail`.
- **`lib/auth-context.tsx`** — React context holding the current user;
  `useRequireAuth()` redirects to `/login` once hydration finishes with
  no user.
- **`lib/endpoints.ts`** — one typed function per backend endpoint.
- **`lib/types.ts`** — hand-written TS mirrors of the response schemas.
- **App shell** (`app/layout.tsx` + `components/sidebar.tsx`): a grouped
  left sidebar on `lg+`, a scrollable top bar below it, both derived from
  one `NAV` array and hidden until a user is present.
- **Design system** — entirely in `app/globals.css`: CSS custom properties
  for a light and a dark palette, `@theme inline` tokens, and component
  classes (`.card` / `.btn` / `.kpi` / `.table` / `.page-head` /
  `.sidebar`). Pages compose these; restyling is a token edit.
- **Pages** (`app/<route>/page.tsx`): `login`, `register`, `/` (redirect),
  `dashboard` (KPIs, trend + category charts, recent activity),
  `transactions` (filters, recategorize, split modal),
  `spending` (three charts), `anomalies` (feed, re-run, dismiss),
  `ask` (question box, example chips, result table + chart, history),
  `accounts`, `upload` (drop file, then a statements list with
  download/delete), `admin` (metrics), `profile` (identity, data
  counts, sessions + activity), `guide` (in-app usage walkthrough).
- **Charts** — `components/charts/*.tsx`, hand-rolled inline SVG
  (ranked bar, spend trend), themed via CSS variables.
- **Build:** `next build` prerenders every route as a static shell
  (there's no server-side data fetching); data loads client-side after
  auth.

---

## 16. Testing strategy

**~146 tests**, `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`),
run against a **real Postgres** (`<db>_test`, created on demand). CI
provides it as a service container.

### Harness — `tests/conftest.py`
- `test_engine` (session-scoped): creates `<db>_test` if missing,
  `Base.metadata.create_all`, drops everything at the end.
- `db_session` (function-scoped): a fresh session; on teardown deletes
  every table's rows in reverse-FK order so tests are isolated regardless
  of what they committed.
- `client` (httpx `AsyncClient` + `ASGITransport`): overrides `get_db` to
  yield the test's session.
- `authed_client`: registers + logs in a fixture user, sets the bearer.
- autouse `_disable_rate_limiting`: turns the limiter off (the whole
  suite shares one process and one client IP) and `.reset()`s it around
  each test.
- autouse `_isolate_upload_storage`: points `UPLOAD_STORAGE_DIR` at a
  per-test `tmp_path`.

### What's mocked — only the LLM boundary
- Tier 3 tests monkeypatch `categorize_merchants_batch` with a fake
  returning a fixed `LLMCallResult`.
- Text-to-SQL tests monkeypatch `llm_selector.select_template` with a
  fake returning a fixed `TemplateSelection` (or raising, for the outage
  path).
Nothing else is mocked — parsing, matching, anomaly detection, the DB,
and all HTTP flows run for real.

### Coverage by area
| file | covers |
|---|---|
| `test_csv_parsing`, `test_pdf_parsing`, `test_ocr_parsing`, `test_column_classifier`, `test_sign_convention` | Tier 1: layouts, column roles, all sign conventions, OCR degrade |
| `test_bank_profile_reuse` | cold detection → profile learned → same/similar layout reuses it, different layout doesn't |
| `test_parse_failures`, `test_statement_upload`, `test_statement_stats` | failure logging, upload endpoint, rollups |
| `test_merchant_cleaner`, `test_categorization_matcher`, `test_categorization_service` | cleaning, exact/fuzzy, the `grocery mart`/`bart` false-positive |
| `test_tier3_categorization`, `test_promotion_job`, `test_manual_recategorization` | batched LLM fallback, promotion threshold + consistency, correction feedback |
| `test_transaction_list`, `test_transaction_split`, `test_transaction_stats`, `test_spending_views`, `test_recurring_detection` | list/filter, split-sum validation, spend attribution, periodicity |
| `test_anomaly_detection` | injected-anomaly recall = 1.0, correct driving feature, dismissal stickiness + soft/hard suppression, user scoping |
| `test_text_to_sql` (13) | right template → right numbers, all four decline paths, history scoping, **two user-scoping bypass attempts** |
| `test_audit_log` (6) | every sensitive action writes a row, activity endpoint scoped, delete removes the file |
| `test_rate_limit` (2) | the window bites; scopes are independent |
| `test_signed_download` (6) | owner round-trip, non-owner, tampered, expired, cross-statement token |
| `test_auth` (15) | rotation, reuse → family revoke, session list/revoke, cross-user rejection |

### Frontend CI
`npm run lint` (ESLint) + `npm run build` (`tsc` + `next build`).

---

## 17. Infrastructure, CI, migrations, seed data

### Docker
- **`backend/Dockerfile`** — `python:3.12-slim`, `uv` copied from its
  published image, `tesseract-ocr` apt-installed (so the OCR path is
  genuinely exercised), `uv sync --frozen --no-dev` in two layers (deps
  then project), `CMD uv run uvicorn app.main:app --host 0.0.0.0 --port
  8000`.
- **`frontend/Dockerfile`** — multi-stage `node:24-slim`: `npm ci` →
  `next build` → runner with `npm start`. Takes
  `NEXT_PUBLIC_API_BASE_URL` as a build arg (inlined into the client
  bundle at build time); empty → the `http://localhost:8000` fallback.
- **`docker-compose.yml`** (dev) — `postgres:16-alpine` (healthchecked,
  named volume), `backend` (waits for pg healthy; bind-mounts `./backend`
  + a named volume for `.venv`; its `command` runs `alembic upgrade head`
  before uvicorn so a bare `docker compose up` works end to end),
  `frontend` (depends on backend).
- **`docker-compose.prod.yml` + `deploy/`** — the production stack:
  `postgres` (named volume, unpublished), `backend` (migrates on start,
  `backend_uploads` volume), `frontend` (built with the public API URL),
  and **Caddy** as the only published service. `deploy/Caddyfile` serves
  the frontend at `/` and `handle_path /api/*` strips the prefix and
  proxies to the backend — one origin, no CORS, one auto-renewed TLS
  cert. Secrets come from a gitignored `.env.prod` (`.env.prod.example`
  is the template); `deploy/deploy.sh` builds + migrates + restarts.
  Full runbook: [`DEPLOY.md`](./DEPLOY.md).

### CI — `.github/workflows/ci.yml`
Three jobs on push/PR:
1. **backend** — Postgres service container, `uv python install 3.12`,
   `uv sync --locked`, apt `tesseract-ocr`, `ruff check .`, `pytest -q`.
2. **frontend** — `npm ci`, `npm run lint`, `npm run build`.
3. **docker-build** — `docker compose build` sanity check (needs 1 & 2).

### Migrations
`alembic/env.py` builds an async engine from `DATABASE_URL`,
`from app.models import *` for autogenerate metadata. Eight linear
migrations.

### Seed scripts (`backend/scripts/`)
- **`seed_merchant_lookup.py`** — the ~60 `seed` rules. Idempotent.
- **`seed_demo.py`** — creates `demo@fintell.app` / `demo-password-123`,
  generates ~6 months of synthetic transactions across **three "banks" in
  three different CSV layouts** (clean standard / debit-credit columns /
  reordered positive-debit), two statements per bank (so the second
  reuses the learned profile), injects two anomalies into the later
  statements, and pushes everything through the **real** upload pipeline.
  `--reset` wipes the demo user first. All data is generated — no real
  financial data.
- **`generate_statement_fixtures.py`** — one-off generator for the
  committed test fixtures (`--extra fixture-gen` for `pillow` +
  `reportlab`). Never run by tests/CI.

---

## 18. Configuration reference

All fields on `app/core/config.Settings` (env var = UPPER_SNAKE of the
field). Defaults shown.

| setting | default | meaning |
|---|---|---|
| `environment` | `development` | free-form label |
| `database_url` | `postgresql+asyncpg://finance:finance@localhost:5432/finance` | async DSN |
| `jwt_secret_key` | dev placeholder | HS256 secret for access + download tokens |
| `jwt_algorithm` | `HS256` | |
| `access_token_expire_minutes` | `15` | |
| `refresh_token_expire_days` | `30` | |
| `llm_api_key` | `None` | unset ⇒ Tier 3 and `/ask` decline gracefully |
| `llm_base_url` | `https://api.openai.com/v1` | any OpenAI-compatible endpoint |
| `llm_model` | `gpt-4o-mini` | |
| `categorization_confidence_threshold` | `0.75` | fuzzy-match acceptance floor (Tier 2) |
| `upload_storage_dir` | `uploads` | root for stored statement files |
| `max_upload_size_bytes` | `15 MiB` | rejected with 413 above this |
| `bank_profile_fuzzy_match_threshold` | `90.0` | header-similarity floor for profile reuse |
| `pdf_structure_detection_page_sample` | `3` | pages sampled by the structure sniffer |
| `ocr_min_confidence` | `40.0` | mean OCR confidence below this ⇒ `failed_needs_manual` |
| `llm_max_batch_size` | `20` | distinct merchants per Tier 3 call |
| `llm_request_timeout_seconds` | `30.0` | |
| `llm_cost_per_1k_prompt_tokens` | `0.00015` | for cost estimation only |
| `llm_cost_per_1k_completion_tokens` | `0.0006` | " |
| `llm_promotion_min_occurrences` | `3` | consistent LLM decisions before promotion |
| `anomaly_min_transactions` | `30` | below this, no model is fit |
| `anomaly_contamination` | `0.05` | IsolationForest `contamination` |
| `anomaly_explain_z_threshold` | `2.0` | robust-z bar for a feature to be a "driver" |
| `text_to_sql_min_confidence` | `0.6` | below this selection confidence ⇒ decline |
| `rate_limit_enabled` | `True` | master switch (off in tests) |
| `rate_limit_auth_max_requests` / `_window_seconds` | `10` / `60` | login/register/refresh |
| `rate_limit_upload_max_requests` / `_window_seconds` | `20` / `60` | upload |
| `download_url_ttl_seconds` | `300` | signed-URL lifetime |
| `frontend_origin` | `http://localhost:3000` | the one CORS origin allowed with credentials |

---

## 19. Known limitations and future work

- **Uploaded files are plaintext on local disk.** Add Fernet at-rest
  encryption (key from config) and/or move to object storage behind the
  existing signed URLs.
- **Rate-limit and anomaly-suppression state are in-process** — they
  reset on restart and aren't shared across workers. Redis fixes both.
- **No admin RBAC.** `/admin/*` is behind ordinary auth.
- **Tier 3 disabled without a key** in the reference environment, so the
  measured deterministic-categorization rate is 100 %. With a real key
  and repeated uploads the interesting metric is the Tier 3 escalation
  rate falling as the promotion job runs.
- **`transactions.export`** is a defined audit action with no endpoint
  yet — a filtered-CSV export is the natural addition.
- **Recurring detection** is a heuristic; it won't catch irregular-but-
  real subscriptions (annual renewals with a free trial, usage-billed
  services).
- **OCR** is local Tesseract — weaker than a cloud OCR service, by
  choice, to keep statement files off third-party infrastructure.
- **Node 20 deprecation warnings** in CI (GitHub forcing actions to Node
  24); harmless until the pinned action majors are bumped.

---

*Every design decision above was made to be explainable in an interview.
If something here looks over-engineered, it's usually because the boring
version was tried first and this is what it took to be correct.*
