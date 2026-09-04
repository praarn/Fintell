# backend/app/services/categorization/ — explanation

Tiers 2 & 3: assign one of 14 categories to every transaction, cheapest
method first, and get cheaper over time as the same merchants recur. Full
rationale is in the root
[`IMPLEMENTATION.md`](../../../../IMPLEMENTATION.md) §8.

## The flow

```
categorize_statement_transactions(db, statement)     ← Tier 2, runs right after parsing
│
├─ merchant_cleaner.clean(raw_merchant)
│     regex-only: strip payment-rail boilerplate (POS/UPI/NEFT/ACH/…),
│     UPI handles, long reference codes, trailing US state codes →
│     a lowercase matching key. Most of the "AI-sounding normalization
│     problem" is solved here, before any matching runs.
│
├─ MerchantMatcher (built ONCE per statement from a single
│  `SELECT * FROM merchant_lookup`, never re-queried per row)
│     ├─ exact dict lookup       → rule_exact,  confidence 1.0
│     ├─ RapidFuzz token_set_ratio, must clear a score floor (60) AND
│     │  a confidence threshold (0.75)   → rule_fuzzy
│     └─ no match                → categorization_method stays NULL,
│                                   normalized_merchant is set — this is
│                                   exactly the set Tier 3 picks up
│
tier3.py (Phase 4, batched, after Tier 2 for the whole statement)
│     no-ops immediately if LLM_API_KEY is unset
├─ group unresolved transactions by cleaned merchant string
│     (several transactions sharing a merchant cost ONE decision)
├─ chunks of ≤ LLM_MAX_BATCH_SIZE (20) distinct merchants, one
│  chat.completions.parse call each, response_format constrains the
│  category to the 14-value enum — a failed chunk is skipped, not fatal
├─ per call   → llm_batch_calls row (tokens, estimated_cost_usd)
└─ per merchant → apply category to all its rows (method = llm) +
                  llm_decision_log row

after the batches → db.commit() → run_promotion_job(db) inline
```

## Files

| File | Role |
| --- | --- |
| `service.py` | Tier 2 entry (`categorize_statement_transactions`); also `recategorize_transaction` — the manual-correction feedback path |
| `matcher.py` | `MerchantMatcher` — exact dict then RapidFuzz, confidence-gated |
| `merchant_cleaner.py` | raw descriptor → canonical lowercase matching key |
| `tier3.py` | batches unresolved transactions to the LLM, logs cost + decisions |
| `llm_client.py` | the actual OpenAI-compatible structured-output call |
| `promotion.py` | turns repeated, agreeing LLM answers into permanent rules |
| `constants.py` | the 14 `CATEGORIES` + `CategoryLiteral`, reused by every schema and the LLM `response_format` so drift is impossible |
| `seed.py`, `seed_data.py` | ~60 starter merchant→category rules (`match_type = seed`), idempotent, run via `scripts/seed_merchant_lookup.py` |

## The closed loop that lowers the Tier 3 rate over time

- **Promotion** (`promotion.py`): `GROUP BY cleaned_merchant` over
  un-promoted `llm_decision_log` rows, `HAVING count() ≥
  LLM_PROMOTION_MIN_OCCURRENCES` (3) **and** exactly one distinct
  category for that merchant → upserted into `merchant_lookup`
  (`match_type = llm_promotion`). Also runnable on demand via
  `POST /admin/promotion-job/run`.
- **Manual correction** (`service.recategorize_transaction`, `PATCH
  /transactions/{id}/category`): fixes the one transaction
  (`manual_user_correction`, confidence 1.0) **and** upserts a
  `merchant_lookup` row (`match_type = user_correction`) so the same
  merchant resolves at Tier 2 next time — the same mechanism as
  promotion, just triggered by a person instead of a count.

## Notes

- The 14 categories are defined in exactly one place
  (`constants.py`) — never hand-typed elsewhere.
- Every automated decision is attributable: `categorization_method` on
  the transaction says which tier decided, and Tier 3 additionally logs
  to `llm_batch_calls` / `llm_decision_log`.
- With `LLM_API_KEY` unset, Tier 3 and promotion are inert — Tier 2 and
  manual correction still work, so the app degrades, it doesn't break.
