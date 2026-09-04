# frontend/src/app/admin/ — explanation

"Metrics & cost" — the live view of `GET /admin/metrics`
(`metrics_service.compute_resume_metrics`), i.e. the numbers that back
the project's "defensible over impressive" claims. **Not real admin** —
same auth as every other page, no RBAC (see the backend's
`app/api/admin.py` comment).

## What it shows

- **Categorization**: % resolved without the LLM, % escalated to Tier 3
  (with merchant + batch-call counts), estimated LLM spend.
- **Parsing**: % of statements served by a learned bank profile, count
  of distinct profiles learned, and the text-to-SQL match rate
  (answered / total questions).
- A full breakdown of `categorization_by_method`, sorted descending by
  count.

## Notes

- Every number here is computed **live** from the database on each
  page load — there's no cached/precomputed metrics table — so the
  numbers move with real usage rather than being a static claim.
- This is the same `ResumeMetrics` payload the dashboard's bottom row
  renders a condensed version of.
