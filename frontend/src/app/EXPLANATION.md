# frontend/src/app/ — explanation

Next.js App Router tree. Every route is a client component
(`"use client"`) — there is no server-side data fetching anywhere in
this app; each page renders a static shell then fetches its own data
after auth hydrates. Full rationale: root
[`IMPLEMENTATION.md`](../../../IMPLEMENTATION.md) §15.

## Shell

- `layout.tsx` — the one root layout: wraps everything in
  `<AuthProvider>`, then `<Sidebar>` (desktop) + `<MobileTopBar>` +
  `<main>`. Every route renders inside this.
- `globals.css` — the entire design system: CSS custom properties for
  light/dark, `@theme` tokens, and the component classes (`.card`,
  `.btn`, `.kpi`, `.table`, `.sidebar`, `.page-head`) every page reuses.
  Restyle by editing token values here, not by touching individual
  pages.
- `page.tsx` (`/`) — no content of its own; redirects to `/dashboard` or
  `/login` once `useAuth()` finishes hydrating.

## Routes

Each folder below is one route with its own `page.tsx`; none currently
nest further.

| Route | Purpose |
| --- | --- |
| `dashboard/` | KPI row, spend-trend + category charts, recent transactions |
| `transactions/` | filter bar, inline recategorize, split modal |
| `spending/` | totals + three ranked/trend charts |
| `ask/` | question box, example chips, answer table + chart |
| `anomalies/` | flag feed with drivers, re-run detection, dismiss |
| `accounts/` | create / list accounts |
| `upload/` | pick any file → parse result → statement list |
| `admin/` | live "does the cost-aware design work" metrics |
| `profile/` | identity, data counts, sessions, activity log |
| `guide/` | in-app usage walkthrough (works signed out too) |
| `login/`, `register/` | the only two routes reachable without a session |

## Notes

- Every route except `login/`, `register/`, `guide/`, and `/` itself
  calls `useRequireAuth()` (`lib/use-require-auth.ts`) at the top, which
  redirects to `/login` once hydration finishes and no user is present —
  there's no middleware-level route guard.
- Because everything is a client component, `layout.tsx` and every
  `page.tsx` prerender as an empty/loading shell at build time; real
  content only appears after the browser runs the auth hydration effect.
- Nav structure lives in exactly one place —
  `components/sidebar.tsx`'s `NAV` array — not duplicated per route.
