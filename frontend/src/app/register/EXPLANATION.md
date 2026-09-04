# frontend/src/app/register/ — explanation

Email/password sign-up calling `useAuth().register`, which itself calls
`endpoints.register` then immediately `endpoints.login` (the backend has
no auto-login-on-register), before redirecting to `/transactions`.

## Notes

- `minLength={8}` on the password input mirrors the backend's
  `UserCreate.password: Field(min_length=8, max_length=128)` — a
  client-side nicety only; the backend still validates and is the real
  boundary (a request that skips the browser gets a 422, not a bypass).
- No password-confirmation field and no email-verification step — this
  is a demo-scale auth flow (root `IMPLEMENTATION.md` §12.5 lists the
  other deliberate security trade-offs in the project, e.g. no admin
  RBAC and plaintext-on-disk uploads).
