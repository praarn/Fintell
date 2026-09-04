# backend/app/services/ — explanation

All of the app's real logic, deliberately framework-free: no FastAPI
imports, no request/response objects, just functions that take an
`AsyncSession` plus plain arguments. The `api/` routers are thin wrappers
that call into here. Four sub-packages hold the multi-step pipelines; the
loose `*_service.py` files are the simpler per-resource logic.

For the deep rationale — every tier, every rejected alternative — see the
root [`IMPLEMENTATION.md`](../../../IMPLEMENTATION.md) §7–§12. This file is
just the map of the folder.

## Layout

```
parsing/            Tier 1 — turn an uploaded file into Transaction rows
                    (IMPLEMENTATION.md §7). Never raises to the caller;
                    an unresolvable file becomes a failed_needs_manual
                    statement + a logged ParseFailure.
  pipeline.py         entry point: parse_statement() — drives the whole
                     Tier 1 run and mutates the Statement in place
  structure_sniffer.py  file_type + structure (CSV / PDF-table / PDF-text
                     / scanned) from the bytes and filename
  profile_service.py    the reuse-vs-cold decision: match a stored
                     bank_profile by fingerprint, else run cold detection
  fingerprint.py        column/layout signature used to find a profile
  column_classifier.py  header detection + column-role assignment
                     (date / description / amount / debit / credit / balance)
  sign_convention.py    resolve negative-for-debit vs separate columns vs
                     balance-delta inference
  csv_parser.py, pdf_table_parser.py, pdf_text_parser.py, ocr_parser.py
                     the four format-specific readers → a common row grid
  grid_parser.py        shared: grid of cells → ParsedRow list
  text_utils.py         cell normalisation, amount/date coercion helpers
  types.py              ParsedRow, UnresolvableStructureError, reason codes

categorization/     Tiers 2 & 3 — assign one of 14 categories per txn
                    (IMPLEMENTATION.md §8)
  service.py           Tier 2 entry: exact/fuzzy match against
                     merchant_lookup; also recategorize_transaction()
                     (the manual-correction feedback path)
  matcher.py            MerchantMatcher — exact then RapidFuzz, with a
                     confidence threshold
  merchant_cleaner.py   raw descriptor → canonical merchant string
  tier3.py             Tier 3: batch the still-uncategorized txns to the
                     LLM (one call per batch), logged to llm_batch_calls
  llm_client.py         OpenAI-compatible structured-output call
  promotion.py          the promotion job — turns repeated, agreeing LLM
                     answers into permanent merchant_lookup rules
  constants.py          the 14 categories + match/method enums
  seed.py, seed_data.py the starter merchant_lookup rows

anomaly/            Per-user IsolationForest with explainability
                    (IMPLEMENTATION.md §10)
  features.py           hand-built spending feature space + the merchant/
                     category keys used for dismissal suppression
  detector.py           fit one model per user, score, and derive the
                     human-readable "why this was flagged" drivers
  service.py            orchestration: refit → reconcile the anomaly_flags
                     table → serve the feed → handle dismissals (which
                     feed back into the next refit as "known normal")

text_to_sql/       "Ask your finances" (IMPLEMENTATION.md §11)
  templates.py         the fixed, reviewed query-template registry — the
                     only SQL that can run; each is user-scoped
  llm_selector.py       the LLM's only job: question → template id +
                     params. Never sees the DB, the schema, or SQL.
  service.py            answer_question(): select → Pydantic-validate
                     params → run the builder → numbers + summary, or an
                     honest logged decline. Every outcome → query_template_log

account_service.py      CRUD for user-defined accounts
statement_service.py    statement list/detail, signed-download issuance
transaction_service.py  the unified GET /transactions list + splits
recurring_service.py    group transactions into recurring series (§9)
auth_service.py         register / login / refresh-rotation + reuse detection
audit_service.py        write + read the security audit_log (§12)
metrics_service.py      the live "cost-aware design works" numbers behind
                        /admin
```

## How a statement flows through here

```
POST /statements/upload (api/statements.py)
  → parsing/pipeline.parse_statement          Tier 1  → Transaction rows
  → categorization/service.categorize_...      Tier 2  → most rows categorized
  → categorization/tier3 (Phase 4, batched)    Tier 3  → the rest, via LLM
  → anomaly/service.run_anomaly_detection      best-effort refit for the user
```

## Notes

- **The LLM is optional and only appears in three places** — `tier3.py`,
  `categorization/promotion.py` (indirectly), and `text_to_sql/llm_selector.py`.
  With no API key configured, each degrades to a logged "unavailable" and
  the deterministic tiers still work.
- **Every automated decision is logged to its own table** —
  `llm_batch_calls` / `llm_decision_log` (categorization), `anomaly_flags`
  (drivers stored inline), `query_template_log` (ask), `parse_failures`
  (Tier 1), and `audit_log` (security).
- **Services never import from `api/`.** Dependency direction is one-way:
  `api/` → `services/` → `models/` + `core/`.
- Functions here take an `AsyncSession` and never open their own
  transaction — the caller (router or script) owns commit/rollback.
