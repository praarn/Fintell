# backend/app/services/text_to_sql/ — explanation

"Ask your finances": answer a natural-language question about the user's
own spending with a real, auditable aggregate query — never LLM-generated
SQL, never a vector store. Full rationale is in the root
[`IMPLEMENTATION.md`](../../../../IMPLEMENTATION.md) §11.

## Why templates, not generated SQL, not RAG

Transaction Q&A is a structured-data problem. Embedding numeric rows and
retrieving by similarity discards the precision a real aggregate query
keeps. Letting the LLM emit SQL creates an injection surface, a
cross-user-leak risk, and an unauditable query surface. So the LLM never
sees the database, the schema, or SQL — it only ever picks a template
name and fills in typed parameters.

## The flow

```
service.answer_question(db, user_id, question)
│
├─ no LLM_API_KEY                          → decline "not configured" (logged)
│
├─ llm_selector.select_template(question)
│     one chat.completions.parse call, response_format = TemplateSelection
│     { template_name: Literal[<the 6 names>, "none"], confidence: float,
│       params: SelectionParams }   ← flat union of every template's
│       params, all optional, extra="ignore"
│     the model CANNOT return a name outside the 6 templates — a
│     module-level assert keeps the Literal in sync with the registry
│   raises                                 → decline "temporarily unavailable" (logged)
│
├─ template_name == "none" or
│  confidence < TEXT_TO_SQL_MIN_CONFIDENCE (0.6)
│                                           → decline "no supported query fits" (logged)
│
├─ re-validate selection.params against the CHOSEN template's own
│  Pydantic model
│   ValidationError                         → decline "matched X but couldn't
│                                              fill it in — <first error>" (logged)
│
└─ run the template — Transaction.user_id == user_id is a literal filter
   IN THE BUILDER, never from anything the LLM produced — and log the
   answered row (template, confidence, validated params, summary)
```

Every outcome — answered or declined — writes a `query_template_log` row.
That table is where the honest template-match rate comes from.

## The template registry — `templates.py`

Six reviewed, parameterized templates, each a `QueryTemplate(name,
description, params_model, run)`:

| template | params model | returns |
| --- | --- | --- |
| `total_spend_in_period` | `PeriodParams` (start, end, optional category) | one number |
| `spend_by_category_in_period` | `PeriodParams` | rows + bar chart |
| `top_merchants_in_period` | `TopNPeriodParams` (+ limit 1–50) | rows + bar chart |
| `compare_spend_between_periods` | `ComparePeriodsParams` (two ranges) | A vs B + delta + % |
| `monthly_spend_trend` | `TrendParams` (months 1–24, optional category) | rows + line chart |
| `largest_transactions` | `TopNPeriodParams` | rows |

Param models use `model_config = ConfigDict(extra="ignore")`, so a
completion that stuffs a `user_id` (or anything else) into its params has
it silently dropped. Date-order (`end ≥ start`) is validated by a
`model_validator`. Spend is always `amount < 0`, reported as positive
magnitudes.

## Files

| File | Role |
| --- | --- |
| `templates.py` | the fixed, reviewed query-template registry — the only SQL that can run; every template is user-scoped in its own builder |
| `llm_selector.py` | the LLM's only job — question → template name + confidence + params |
| `service.py` | `answer_question()` — select → validate → run → log, or an honest logged decline at every failure point |

## Notes

- Two tests specifically prove that an adversarial `SelectionParams`
  carrying another user's id plus a 2000–2100 date range still returns
  only the caller's data — once through the endpoint, once directly at
  the param-model layer.
- Adding a query means adding a template + params model to
  `templates.py` and a line to the selector's prompt — never touching
  how the LLM's output reaches the database.
