# frontend/src/app/accounts/ — explanation

Simple create + list for user-defined accounts. A form
(`display_name` required, `bank_name` optional, `account_type` one of
`checking`/`savings`/`credit_card`/`other`) posts via `createAccount`
and appends the result to local state — no full refetch needed since the
create response is the full `Account` object.

## Notes

- No edit/delete UI here — matches the backend, which only exposes
  `POST`/`GET /accounts` (see `../../../api/EXPLANATION.md`).
- The page copy explains the alternative path explicitly: a statement
  doesn't need a pre-created account — a `bank_hint` on upload
  auto-provisions a lightweight one (`get_or_create_account_for_bank_hint`
  on the backend).
