# frontend/src/app/login/ — explanation

Email/password form calling `useAuth().login`, then `router.replace`s to
`/transactions` on success. Errors from `ApiError` show the backend's
actual `detail` string (e.g. "Invalid email or password") rather than a
generic message.

## Notes

- Advertises the demo credentials (`demo@fintell.app` /
  `demo-password-123`) directly on the page, and links to `/guide` for
  anyone unsure what to do next — this is the only auth-gated area of
  the app reachable with zero prior context.
- Rate-limited on the backend (`auth_rate_limit`, 10/60s per IP) but the
  page itself does no client-side throttling — a 429 just surfaces
  through the same `ApiError` path as any other failure.
