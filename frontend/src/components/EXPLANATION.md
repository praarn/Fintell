# frontend/src/components/ — explanation

Reusable UI shared across routes — everything else lives in its own
route folder under `app/`.

## Files

| File | Role |
| --- | --- |
| `sidebar.tsx` | exports `Sidebar` (desktop, grouped nav) and `MobileTopBar` (scrollable top bar); both derive their links from one `NAV: NavGroup[]` array, and both render nothing (`return null`) when no user is signed in |
| `categorization-badge.tsx` | `CategorizationBadge` — maps a transaction's `categorization_method` (`rule_exact` / `rule_fuzzy` / `llm` / `manual_user_correction` / null) to a labeled, colored chip |
| `split-transaction-modal.tsx` | `SplitTransactionModal` — the ≥2-row category/amount split form; validates the rows sum to the parent amount client-side before calling `splitTransaction` |
| `charts/` | hand-rolled inline-SVG charts, no charting library |

### `charts/`

| File | Role |
| --- | --- |
| `ranked-bar-chart.tsx` | horizontal bar chart for ranked data (top merchants, spend by category) |
| `spend-trend-chart.tsx` | line/area chart for the monthly spend trend |

Both are plain SVG sized with a `viewBox` (so they scale to their
container, no JS resize listeners) and themed entirely through CSS
custom properties (`--viz-text-primary`, etc.) so they follow light/dark
mode for free. Both render an explicit "No data yet." state rather than
an empty chart.

## Notes

- Nothing here calls `fetch`/`apiRequest` directly — components receive
  already-fetched data as props; data loading stays in the page that
  uses them.
- `CATEGORIES` (used by the split modal) comes from `lib/types.ts`, kept
  in sync with the backend's `CategoryLiteral` by hand.
