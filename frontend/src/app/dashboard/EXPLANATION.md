# frontend/src/app/dashboard/ — explanation

The "/" landing page after login. One `useEffect` fires five reads in
parallel (`Promise.all`) once `useRequireAuth()` resolves a user:
spending-by-category, a 12-month trend, the 6 most recent transactions,
anomaly stats, and the admin resume metrics — the last two are
`.catch(() => null)`'d so a metrics hiccup never blocks the page.

## What it shows

- 4 KPI tiles: last month's spend (with a ▲/▼ vs. the prior month),
  monthly average, largest category all-time, and open-anomaly count
  (linking to `/anomalies` when > 0).
- `SpendTrendChart` + top-7 `RankedBarChart` by category, side by side.
- A 6-row recent-transactions table linking to `/transactions`.
- If `metrics` loaded: the three "cost-aware design works" numbers (%
  categorized deterministically, % via a learned profile, estimated LLM
  spend) — the same numbers as `/admin`, condensed.

## Notes

- All money values here are derived client-side from `SpendingTrendPoint`
  strings (`parseFloat`) — the backend returns decimals as strings to
  avoid float-precision surprises in JSON.
- `deltaPct` is `null` (not 0) when there's no prior month, so the UI can
  say "no prior month to compare" instead of a misleading 0%.
