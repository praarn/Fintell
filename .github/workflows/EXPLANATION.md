# .github/workflows/ — explanation

One workflow, `ci.yml`. Runs on every push to `main` and every pull
request. Three jobs, the third gated on the first two.

## Jobs

| Job | Runs | Key steps |
| --- | --- | --- |
| `backend` | against a real `postgres:16-alpine` service container (not mocked) | `astral-sh/setup-uv` → `uv python install 3.12` → `uv sync --locked` → install `tesseract-ocr` via apt (needed for the OCR parser tests) → `ruff check .` → `pytest -q` |
| `frontend` | Node 24, npm-cached | `npm ci --ignore-scripts` → `npm run lint` → `npm run build` |
| `docker-build` | `needs: [backend, frontend]` | `docker compose build` — a sanity check that the images still build, not a deploy |

## Notes

- **`DATABASE_URL` and `JWT_SECRET_KEY` are fixed CI-only values**
  (`ci-test-secret-key-thats-long-enough-for-hs256-hmac`), set as job
  `env`, not secrets — there's nothing sensitive to protect since the
  Postgres instance only exists for the duration of the job.
- The backend job installs Tesseract at CI time rather than baking a
  custom runner image — the same tradeoff as the `Dockerfile` (apt
  install at build time).
- Nothing here runs migrations — `pytest`'s `conftest.py` builds the
  test schema directly via `Base.metadata.create_all`, so a broken
  Alembic revision would only be caught by actually running
  `alembic upgrade head` (e.g. via `docker-build`'s compose build +
  manual run, or locally).
- `--ignore-scripts` on `npm ci` skips any package postinstall scripts —
  a supply-chain hardening default, not needed for build correctness
  here since nothing in `package.json` currently relies on one.
