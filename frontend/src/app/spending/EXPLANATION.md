# frontend/src/app/spending/ — explanation

Outflow-only spending breakdown, optionally scoped to one account via a
dropdown. Three data points fetched together whenever `accountId`
changes: `getSpendingByCategory`, `getSpendingTrend(6, accountId)`, and
`getTopMerchants(limit=8)`.

## What it shows

- 3 stat cards: all-time total spend, average per month (over however
  many trend months came back), largest category.
- `SpendTrendChart` (6-month trend).
- Two `RankedBarChart`s side by side: spend by category, top 8
  merchants.

## Notes

- All figures are outflows reported as positive magnitudes — the page
  lead says so explicitly, matching the backend's `/spending/*`
  convention (§9 in root `IMPLEMENTATION.md`).
- Category labels get their underscore replaced with a space
  (`groceries` stays as-is, `food_delivery` → "food delivery") purely
  for display; the underlying value sent back to the API is untouched.
