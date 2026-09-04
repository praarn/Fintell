# backend/tests/ — explanation

~146 pytest tests run against a real throwaway Postgres database — no
mocked DB, no in-memory SQLite. The only mocked boundary in the entire
suite is the LLM API call itself. Full rationale: root
[`IMPLEMENTATION.md`](../../IMPLEMENTATION.md) §16.

## Harness — `conftest.py`

- `test_engine` (session-scoped): creates `<database_name>_test` via a
  raw `asyncpg` admin connection if it doesn't exist, then
  `Base.metadata.create_all` — the suite never runs Alembic migrations.
- `db_session` (per-test): a fresh session; teardown deletes every table
  in reverse dependency order so tests don't leak state into each other
  regardless of what was committed.
- `client`: an `httpx.AsyncClient` wired straight to the FastAPI `app`
  via `ASGITransport`, with `get_db` overridden to the test session — no
  real network, no separate server process.
- `authed_client`: registers + logs in one fixture user and preloads the
  bearer token, for tests that don't care about auth itself.
- Two autouse fixtures: rate limiting is **off** by default (the whole
  suite shares one process and client IP; `test_rate_limit.py`
  re-enables it explicitly) and uploaded files go to a per-test
  `tmp_path`, never the real `backend/uploads/`.

## Fixtures — `fixtures/statements/`

Static, committed files exercising every Tier 1 structure: clean CSV,
debit/credit-column CSV, malformed rows, reordered columns, single
running-balance column, banner rows, an extractable PDF table, a
text-only PDF, and a scanned (OCR-required) PDF. Regenerated only by
`scripts/generate_statement_fixtures.py`, never by the tests themselves.

## Coverage by area

| Area | Files |
| --- | --- |
| Auth & sessions | `test_auth.py` |
| Parsing (Tier 1) | `test_csv_parsing.py`, `test_pdf_parsing.py`, `test_ocr_parsing.py`, `test_column_classifier.py`, `test_sign_convention.py`, `test_bank_profile_reuse.py`, `test_parse_failures.py`, `test_statement_upload.py`, `test_statement_stats.py` |
| Categorization (Tiers 2/3) | `test_categorization_matcher.py`, `test_categorization_service.py`, `test_merchant_cleaner.py`, `test_tier3_categorization.py`, `test_promotion_job.py`, `test_manual_recategorization.py` |
| Transactions / views | `test_transaction_list.py`, `test_transaction_split.py`, `test_transaction_stats.py`, `test_spending_views.py`, `test_recurring_detection.py` |
| Accounts | `test_accounts.py` |
| Anomaly detection | `test_anomaly_detection.py` |
| Ask your finances | `test_text_to_sql.py` |
| Security | `test_audit_log.py`, `test_signed_download.py`, `test_rate_limit.py` |
| Health | `test_health.py` |

## Notes

- **Only the LLM boundary is mocked.** Everything else — Postgres, file
  parsing, OCR, the HTTP layer — runs for real.
- `test_text_to_sql.py` includes an adversarial case: a `SelectionParams`
  carrying another user's id and an out-of-range date window still only
  returns the caller's own data, checked both through the endpoint and
  directly at the param-model layer.
- `test_anomaly_detection.py` asserts recall = 1.0 on a synthetic history
  with two injected anomalies, with only a 0.4 precision floor — the
  "normal" rows are unlabelled and legitimately contain borderline
  cases.
