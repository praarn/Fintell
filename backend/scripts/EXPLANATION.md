# backend/scripts/ — explanation

One-off / operator scripts, run manually with `uv run python
scripts/<name>.py`. Not imported by the app or the test suite.

## Files

| File | Purpose |
| --- | --- |
| `seed_merchant_lookup.py` | inserts the ~60 starter `merchant_lookup` rules (`categorization/seed.py`). Idempotent — only inserts patterns that don't already exist. |
| `seed_demo.py` | creates (or tops up, `--reset` to wipe first) a demo user (`demo@fintell.app`) with a synthetic multi-bank transaction history. Statements are pushed through the **real** upload → parse → categorize pipeline, so the demo also exercises bank-profile reuse (each bank's second statement reuses the profile learned from its first) and Tiers 1–3. Everything generated is synthetic — no real bank, person, or transaction. |
| `generate_statement_fixtures.py` | regenerates the static test fixtures under `tests/fixtures/statements/` (CSV variants + PDFs via `reportlab`/`PIL`). Output is committed; never run by CI or by the tests themselves — only re-run by hand when the fixture set needs to change. |

## Notes

- Each script does `sys.path.insert(0, <backend root>)` so it can `from
  app...` import without being installed as a package or run with
  `-m`.
- All three talk to the database via `app.core.database.async_session_factory`
  directly — no HTTP layer involved, so they work even if the API isn't
  running.
- `generate_statement_fixtures.py` needs the `fixture-gen` extra
  (`reportlab`, `Pillow`) — deliberately kept out of the main dependency
  set since nothing at runtime needs it.
