# frontend/src/app/profile/ — explanation

Identity + the account-security surface: data counts, active sessions,
and the personal audit trail. The one page that touches auth-session
management beyond login/logout.

## Flow

- `refresh()` loads five things in parallel: account/statement counts
  (statement and account lists, plus a `page_size: 1` transaction list
  just to read its `total`), `listSessions()`, and `getActivity(50)`.
- **Sessions**: each row is one refresh-token family (one signed-in
  device/browser). The current session is marked and has no "Revoke"
  button; revoking any other calls `revokeSession(family_id)` then
  refetches. Matches the backend's rotation-family model in
  `auth_service` — revoking a family invalidates that whole device's
  refresh chain, not just one token.
- **Activity**: renders `audit_log` rows via `ACTION_LABELS`, a small
  map from the backend's dot-namespaced action strings
  (`auth.login`, `statement.upload`, …) to human copy; an unmapped
  action falls back to showing the raw string, so a new audit action
  type never breaks the page, it just shows unstyled.

## Notes

- The page's own copy explains the reuse-detection mechanism to the
  user in plain language: "reuse of a rotated-out token revokes the
  whole chain automatically" — this is user-facing documentation of the
  same behavior the backend's `test_auth.py` verifies.
