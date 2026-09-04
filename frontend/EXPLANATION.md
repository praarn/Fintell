# frontend/ — explanation

Next.js 16 (App Router, all client components), TypeScript, Tailwind v4.
A thin, typed client over the backend API — no server-side data fetching;
every route prerenders as a static shell and loads its data after auth.

For the full picture see the root [`IMPLEMENTATION.md`](../IMPLEMENTATION.md)
§15. This file is the folder map.

## Layout

```
src/
  app/
    layout.tsx        the app shell: <Sidebar> + <MobileTopBar> + <main>
    globals.css       the design system — CSS custom properties (light +
                      dark), @theme tokens, and component classes
                      (.card / .btn / .kpi / .table / .sidebar / .page-head)
    page.tsx          "/" — redirects to /dashboard or /login
    dashboard/        KPI row, spend-trend + category charts, recent txns
    transactions/     filter bar, inline recategorize, split modal
    spending/         totals + three ranked/trend charts
    ask/              question box, example chips, answer table + chart
    anomalies/        flag feed with drivers, re-run, dismiss
    accounts/         create / list accounts
    upload/           pick any file → parse result → statement list
    admin/            live "does the cost-aware design work" metrics
    profile/          identity, data counts, sessions, activity log
    guide/            in-app usage walkthrough (works signed-out too)
    login/, register/
  components/
    sidebar.tsx       grouped nav (desktop) + scrollable top bar (mobile)
    nav is derived from one NAV array
    categorization-badge.tsx, split-transaction-modal.tsx
    charts/           hand-rolled inline-SVG ranked-bar + spend-trend,
                      themed via CSS variables, responsive down to phones
  lib/
    api.ts            apiRequest<T>(): bearer injection, query building,
                      single shared in-flight 401 refresh + one retry
    auth-context.tsx  current-user context (login/register/logout)
    use-require-auth.ts  useRequireAuth() — redirects to /login post-hydration
    endpoints.ts      one typed function per backend route
    types.ts          hand-written mirrors of the response schemas
    config.ts         API base URL (NEXT_PUBLIC_API_BASE_URL || localhost)
```

## Run it

```bash
cp .env.local.example .env.local     # NEXT_PUBLIC_API_BASE_URL
npm install
npm run dev                          # :3000
```

## Checks

```bash
npx tsc --noEmit
npm run lint
npm run build
```

## Notes

- **`NEXT_PUBLIC_API_BASE_URL` is inlined at build time.** Unset →
  `http://localhost:8000` (see `lib/config.ts`).
- Tokens live in `localStorage`; the shell (sidebar/top bar) only renders
  when a user is present.
- The design system is entirely in `globals.css` — restyle by editing the
  token values, not the pages.
