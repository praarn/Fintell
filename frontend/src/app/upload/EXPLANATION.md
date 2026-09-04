# frontend/src/app/upload/ — explanation

The Tier 1 entry point: pick any file, optionally attach an account or
type a bank hint, submit, see the parse outcome, and manage past
statements (download via a signed URL, delete).

## Flow

- The account `<select>` and the bank-hint `<input>` are mutually
  exclusive in the UI (the hint field only renders when no account is
  selected) — mirrors the backend's `upload_and_parse_statement`
  precedence: explicit `account_id` wins, else `bank_hint`
  auto-provisions a lightweight account, else the statement stays
  unlinked.
- On success, `result` (the full `StatementOut`) renders as a small
  fact sheet: `parse_status`, `detected_structure`, `parse_method`, rows
  parsed/total, and `error_message` if present — this is the same
  Tier 1 metadata described in root `IMPLEMENTATION.md` §7, surfaced
  directly rather than re-derived.
- **Download**: `getStatementDownloadUrl` mints a short-lived signed
  URL (`core/security.create_download_token`), then `window.open`s
  `${API_BASE_URL}${url}` directly — the browser tab, not `apiRequest`,
  makes that request, since the token itself is the auth (see
  `../../../api/EXPLANATION.md`).
- **Delete**: gated behind a native `window.confirm` (the one place in
  the app that uses a blocking browser dialog), since it cascades to the
  statement's transactions.

## Notes

- The page never restricts the file input by extension or MIME type —
  matches the backend's "accept anything, sniff the content" design;
  an unreadable file comes back as a `failed_needs_manual` result, not a
  client-side rejection.
