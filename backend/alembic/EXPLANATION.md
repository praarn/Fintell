# backend/alembic/ — explanation

Database migrations. Eight, linear, no branches — this project has never
needed to merge concurrent migration heads.

## Layout

```
env.py               builds an async engine from Settings.database_url,
                      imports app.models so every table is registered on
                      Base.metadata before autogenerate diffs against it
script.py.mako        template for new revisions
versions/             one file per migration, oldest first:
  7ca738897a8d_create_users_and_refresh_tokens_tables.py
  15bd86c1e4ea_add_statement_parsing_tables.py
  27e97f6a3b7f_add_accounts_and_transaction_splits_...py
  d1796c1bbe9a_add_merchant_lookup_table.py
  2fcfb6b34c40_add_llm_decision_log_and_llm_batch_...py
  b7e2a1f4c9d3_add_anomaly_flags_table.py
  c4d8e2f19a67_add_query_template_log_table.py
  e5f1a9c72b84_add_audit_log_table.py
```

Each migration corresponds to one phase of the project — the order above
is also the build order (auth → parsing → accounts/splits → merchant
lookup → LLM categorization → anomalies → text-to-SQL → security
hardening).

## Run it

```bash
uv run alembic upgrade head          # apply all pending migrations
uv run alembic revision --autogenerate -m "add X"   # after a model change
```

## Notes

- `env.py` runs migrations **online** with an async engine
  (`async_engine_from_config` + `run_sync`) — there's no separate sync
  driver dependency just for Alembic.
- Autogenerate only sees what's imported — `env.py`'s
  `from app.models import *` is what makes a new model in
  `app/models/` show up in the diff at all.
- The test suite (`tests/conftest.py`) does **not** run these
  migrations — it calls `Base.metadata.create_all` directly against a
  throwaway `<db>_test` database, so a schema change only needs a
  migration for the real dev/prod database, not for tests to pass.
