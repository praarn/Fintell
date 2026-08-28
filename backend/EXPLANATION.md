# backend/ — explanation

FastAPI service that does the whole pipeline: parse an uploaded statement,
categorize its transactions, detect anomalies, answer natural-language
questions, and expose it all over a typed HTTP API. Managed with `uv`
(Python 3.12 pinned in `.python-version`).

For the deep design rationale — every table, every rejected alternative —
see the root [`IMPLEMENTATION.md`](../IMPLEMENTATION.md). This file is just
the map of the folder.

## Layout

```
app/
  main.py            FastAPI app, CORS, router wiring
  core/              config (pydantic-settings), async DB engine/session,
                     security (JWT + signed download tokens), rate limiter
  api/               one router per resource — auth, statements,
                     transactions, accounts, anomalies, ask, admin, health
                     deps.py holds get_current_user / get_db
  models/            SQLAlchemy 2 typed ORM models (one file per table)
  schemas/           Pydantic request/response models
  services/          all the real logic, framework-free:
    parsing/         Tier 1 — structure sniff → profile reuse/cold detect →
                     CSV / PDF-table / PDF-text / OCR parsers → grid parser
    categorization/  Tiers 2 & 3 — exact/fuzzy rules, batched LLM fallback,
                     the promotion job that turns LLM answers into rules
    anomaly/         per-user IsolationForest + feature explainability
    text_to_sql/     reviewed query templates + LLM template selector
    *_service.py     statement / transaction / account / audit / metrics
alembic/             migrations (8, linear); env.py builds an async engine
scripts/             seed_merchant_lookup.py, seed_demo.py,
                     generate_statement_fixtures.py (one-off)
tests/               ~146 pytest tests against a real throwaway Postgres
```

## Run it

```bash
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python scripts/seed_merchant_lookup.py
uv run python scripts/seed_demo.py            # optional demo data
uv run uvicorn app.main:app --reload          # :8000, docs at /docs
```

Needs a Postgres reachable at `DATABASE_URL` (`docker compose up -d postgres`
from the repo root is the easy way).

## Tests / lint

```bash
uv run pytest            # needs Postgres; creates + drops <db>_test itself
uv run ruff check .
```

## Notes

- **The LLM is optional.** With `LLM_API_KEY` unset, Tier 3 categorization
  and "Ask your finances" degrade to an honest "unavailable" — no crash.
- **Never raises to the client on a bad file.** An unparseable statement
  becomes a `failed_needs_manual` row with a logged `ParseFailure`.
- **Every automated decision is logged** — categorization method, parse
  method, anomaly drivers, query template, and a security `audit_log`.
- Uploaded files are stored under `UPLOAD_STORAGE_DIR` and only served
  through short-lived signed URLs (`app/core/security.py`).
