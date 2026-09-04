# backend/app/schemas/ — explanation

Pydantic request/response models — the typed contract between `api/` and
the outside world. Kept separate from `models/` (the ORM layer) on
purpose: a schema is a view of a table (or several), never the table
itself, so a column can be hidden, renamed, or computed without touching
the database.

## Files

| File | Covers |
| --- | --- |
| `auth.py` | register/login payloads, `TokenPair`, `SessionOut`, `AuditLogOut` |
| `account.py` | `AccountCreate` / `AccountOut` |
| `statement.py` | `StatementOut`, `TransactionOut`, `ParseFailureOut`, `DownloadUrlOut`, `StatementStatsOut` |
| `views.py` | the transaction-list/split/spending/recurring response shapes (`TransactionListOut`, `SplitRequest`, `SpendingByCategoryOut`, `SpendingTrendPointOut`, `TopMerchantOut`, `RecurringGroupOut`) |
| `categorization.py` | `LLMStatsOut`, `PromotionJobResultOut` — the admin-facing categorization metrics |
| `anomaly.py` | `AnomalyFlagOut`, `AnomalyDetectRunOut`, `AnomalyStatsOut`, `AnomalyDismissRequest` |
| `ask.py` | `AskRequest`, `AskResponse`, `QueryHistoryItem` |
| `admin.py` | `ResumeMetricsOut` |

## Notes

- **`model_config = ConfigDict(from_attributes=True)`** on every schema
  that wraps an ORM row — routers return the SQLAlchemy object directly
  and FastAPI serializes it through the schema.
- `SplitAllocation.category` and other category-bearing fields type
  against `CategoryLiteral` from
  `services/categorization/constants.py` — the same enum the LLM
  `response_format` uses, so a schema can never accept a category the
  categorization system doesn't know about.
- Validation lives here where it's structural (e.g. `SplitRequest`
  requiring ≥ 2 allocations via `field_validator`); anything
  business-rule-shaped (amounts must sum to the parent) is checked in
  `services/` against the loaded row, not in the schema.
