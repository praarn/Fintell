# frontend/src/app/transactions/ — explanation

The cross-statement, cross-account transaction table. Filter by account,
category and merchant search; paginated 25/page; inline recategorize;
split via `SplitTransactionModal`.

## Flow

- `refresh()` (memoized on `[user, accountId, category, search, page]`)
  calls `listTransactions` with the current filters and is re-run by a
  `useEffect` whenever any of them change — a "fetch on filter change"
  pattern with a `isLoading` flag, called out in-line as a deliberate
  simplification over a bigger React Query/Suspense restructure.
- A separate one-time effect loads `accounts` (for the filter dropdown)
  and `getRecurringTransactions()`, flattening every group's
  `transaction_ids` into one `Set<string>` so each row can cheaply show
  a "Recurring" chip.
- `handleRecategorize` calls `PATCH /transactions/{id}/category` then
  patches just that row in local state — no full refetch.
- Any filter change resets `page` to 1 before changing the filter, so
  you never land on an empty page-N of a narrower result set.

## Notes

- A split transaction shows "split across categories" in place of the
  category `<select>` — the parent's `category` is NULL once split (see
  root `IMPLEMENTATION.md` §6 "gotcha" table), so there's nothing
  meaningful to recategorize inline.
- `AmountCell` colors inflows (`n >= 0`, i.e. not negative) positive and
  prefixes them with `+`; outflows render in the default text color —
  the same "outflow = negative" convention as the backend.
