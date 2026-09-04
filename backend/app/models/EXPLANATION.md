# backend/app/models/ — explanation

SQLAlchemy 2 typed ORM models, one file per table, re-exported from
`__init__.py` so `alembic/env.py` can `import app.models` and see every
table on `Base.metadata` for autogenerate. Full schema rationale (every
column, every design choice): root
[`IMPLEMENTATION.md`](../../../IMPLEMENTATION.md) §4.

## Files

| File | Table | Notes |
| --- | --- | --- |
| `user.py` | `users` | email + bcrypt hash |
| `refresh_token.py` | `refresh_tokens` | hash-only storage, `family_id` groups a rotation chain for reuse detection |
| `account.py` | `accounts` | user-defined logical accounts (statements optionally belong to one) |
| `bank_profile.py` | `bank_profiles` | **global, not per-user** — a learned column layout + date format keyed by header fingerprint, never transaction data |
| `statement.py` | `statements` | one row per upload; `parse_status` / `parse_method` / `detected_structure` drive the whole Tier 1 UI |
| `transaction.py` | `transactions` | `amount` is always signed to one convention (positive = inflow, negative = outflow) regardless of the source layout; `categorization_method` is the auditability field |
| `transaction_split.py` | `transaction_splits` | ≥2 category allocations that sum to the parent amount |
| `parse_failure.py` | `parse_failures` | one row per unparseable line/file, with a reason code |
| `merchant_lookup.py` | `merchant_lookup` | the categorization rule table — `match_type` says whether a row came from `seed`, `llm_promotion`, or `user_correction` |
| `llm_batch_call.py` | `llm_batch_calls` | one row per Tier 3 LLM call, with token counts + `estimated_cost_usd` |
| `llm_decision_log.py` | `llm_decision_log` | one row per merchant decision inside a batch; feeds the promotion job |
| `anomaly_flag.py` | `anomaly_flags` | per-transaction flag with severity/score and drivers stored inline as JSON |
| `query_template_log.py` | `query_template_log` | every "ask your finances" outcome, answered or declined |
| `audit_log.py` | `audit_log` | the security audit trail (§12) |

## Notes

- **`user_id` is denormalized onto `transactions`** (not just reached via
  `statement_id`) so per-user queries never need a join — same
  reasoning applies to `account_id`.
- Foreign keys use `ondelete="CASCADE"` for owned children (a user's
  statements/transactions) and `ondelete="SET NULL"` for optional
  associations (a transaction's `account_id`) — deleting an account
  doesn't delete its transactions.
- Models never import from `api/` or `services/` — only from
  `app.core.database.Base` and each other (for `relationship()` type
  hints, guarded by `TYPE_CHECKING`).
- A new table means: add the model here, add it to `__init__.py`'s
  `__all__`, then `alembic revision --autogenerate`.
