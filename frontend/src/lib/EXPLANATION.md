# frontend/src/lib/ — explanation

Everything that talks to the backend or holds cross-page state — no
components, no JSX (except `auth-context.tsx`, which is a provider).

## Files

| File | Role |
| --- | --- |
| `config.ts` | `API_BASE_URL` — `NEXT_PUBLIC_API_BASE_URL` or `http://localhost:8000`. Inlined at build time, since it's a `NEXT_PUBLIC_` var. |
| `api.ts` | `apiRequest<T>()` — the one function every request goes through: bearer-token injection, query-string building, JSON (de)serialization, and 401 handling |
| `auth-context.tsx` | `AuthProvider` + `useAuth()` — holds the current `User | null`, hydrates it from a stored access token on mount, exposes `login`/`register`/`logout` |
| `use-require-auth.ts` | `useRequireAuth()` — thin wrapper that redirects to `/login` once auth hydration finishes with no user |
| `endpoints.ts` | one typed function per backend route (`login`, `getCurrentUser`, `splitTransaction`, …) — the only file that constructs request paths/bodies; everything else calls these, never `apiRequest` directly |
| `types.ts` | hand-written TypeScript mirrors of the backend's Pydantic response schemas, plus `CATEGORIES` (kept in sync with the backend's `CategoryLiteral` by hand) |

## The 401 / refresh flow — `api.ts`

Refresh tokens rotate on every use (the backend enforces reuse
detection), so this can't just retry each failed request independently:

```
apiRequest(path)
  → rawRequest → fetch
      401 and not already a retry
        → is a refresh already in flight? await it, don't start a second
        → else start one: POST /auth/refresh, store the new pair
        → retry the original request once, with isRetry=true
      still failing → throw ApiError(status, detail)
```

The single shared `refreshPromise` is the important part — two
concurrent 401s must await *one* refresh, because a second attempt with
the now-already-rotated-out refresh token would look like theft to the
backend and revoke the whole session.

## Notes

- Tokens live in `localStorage` (`getAccessToken` / `setTokens` /
  `clearTokens` in `api.ts`), not cookies — there's no CSRF surface
  because there's no cookie-based session.
- `ApiError` carries the parsed `detail` from the backend's error body
  so callers can show the server's actual message, not a generic one.
- `endpoints.ts` growing a new function is the entire cost of wiring up
  a new backend route on the frontend — no separate "API client config"
  to update.
