# Commands — running Fintell end to end

Every command needed to build, run, seed, test, and lint the whole project.
Two ways to run it: **Docker Compose** (one command, nothing installed locally
except Docker) or **local dev** (hot reload, needs `uv` + Node).

Ports: backend API on **8000**, frontend on **3000**, Postgres on **5432**.

---

## 0. Prerequisites

| Tool | Version | Needed for |
| --- | --- | --- |
| Docker + Compose v2 | any recent | the Docker path |
| [`uv`](https://docs.astral.sh/uv/) | ≥ 0.11 | backend (local path) — manages Python 3.12, venv, deps |
| Node.js | ≥ 20 (24 tested) | frontend (local path) |
| Postgres 16 | — | only if running the backend locally *without* Docker |

The backend pins **Python 3.12** via `uv` (`backend/.python-version`); `uv`
downloads it automatically, so no system Python 3.12 is required.

---

## 1. Run the whole stack with Docker Compose

```bash
# from the repo root
docker compose up --build
```

This starts Postgres, runs `alembic upgrade head` in the backend container,
then serves the API and the frontend. Open:

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

### Seed data (optional, run once, in another terminal)

```bash
# starter merchant -> category rules
docker compose exec backend uv run python scripts/seed_merchant_lookup.py

# demo user + 6 months of synthetic multi-bank history
docker compose exec backend uv run python scripts/seed_demo.py
```

Demo login: **`demo@fintell.app`** / **`demo-password-123`**
(all seed data is generated — no real financial data).

### Stop / reset

```bash
docker compose down              # stop containers, keep the database volume
docker compose down -v           # stop and delete the database volume (full reset)
```

---

## 2. Run locally for development (hot reload)

### 2a. Database

```bash
docker compose up -d postgres    # just Postgres, on :5432
```

(Or use your own local Postgres 16 with a `finance` DB owned by role `finance`
and update `backend/.env` accordingly.)

### 2b. Backend (FastAPI, port 8000)

```bash
cd backend
cp .env.example .env                              # first time only
uv sync                                           # install deps into .venv
uv run alembic upgrade head                       # create / update tables
uv run python scripts/seed_merchant_lookup.py     # starter merchant rules
uv run python scripts/seed_demo.py                # demo user + synthetic history
uv run uvicorn app.main:app --reload              # serve with hot reload
```

Health check: `curl http://localhost:8000/health` → `{"status":"ok"}`

### 2c. Frontend (Next.js, port 3000)

```bash
cd frontend
cp .env.local.example .env.local     # first time only — points at http://localhost:8000
npm install
npm run dev                          # http://localhost:3000
```

---

## 3. Tests

### Backend (~146 tests, needs a running Postgres)

```bash
cd backend
uv run pytest                       # full suite
uv run pytest -q                    # quiet
uv run pytest tests/test_auth.py    # one file
uv run pytest -k anomaly            # by keyword
```

The suite creates and drops its own `finance_test` database — it never touches
your dev data.

### Frontend

```bash
cd frontend
npx tsc --noEmit     # type-check
npm run lint         # eslint
npm run build        # production build (also type-checks)
```

---

## 4. Lint / format the backend

```bash
cd backend
uv run ruff check .          # lint
uv run ruff check . --fix    # lint + autofix
uv run ruff format .         # format
```

---

## 5. Database migrations (backend)

```bash
cd backend
uv run alembic upgrade head                       # apply all
uv run alembic downgrade -1                       # roll back one
uv run alembic revision --autogenerate -m "msg"   # new migration from model changes
uv run alembic current                            # show current revision
uv run alembic history                            # list revisions
```

With Docker: prefix with `docker compose exec backend`, e.g.
`docker compose exec backend uv run alembic upgrade head`.

---

## 6. Regenerate demo data from scratch

```bash
# local
cd backend && uv run python scripts/seed_demo.py --reset

# docker
docker compose exec backend uv run python scripts/seed_demo.py --reset
```

---

## 7. Optional — LLM features

Tier 3 categorization fallback and the "Ask your finances" box need an
OpenAI-compatible API key. Without one the app degrades honestly (says the
assistant isn't configured). To enable, set in `backend/.env`:

```
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

then restart the backend.

---

## 8. Deploy to production

Two paths, both in **[DEPLOY.md](./DEPLOY.md)**:

- **Free / no card** — `render.yaml` is a Render Blueprint. In the Render
  dashboard: *New → Blueprint → this repo → Apply*.
- **VPS** — a compose file behind Caddy (auto-HTTPS). Short version, on the
  server:

```bash
cp .env.prod.example .env.prod        # set DOMAIN, POSTGRES_PASSWORD, JWT_SECRET_KEY
./deploy/deploy.sh                    # build + migrate + start

# validate the compose file without running it
docker compose --env-file .env.prod -f docker-compose.prod.yml config
```

`.env.prod` is gitignored — never commit real secrets.

---

## Quick reference

| I want to… | Command |
| --- | --- |
| Run everything | `docker compose up --build` |
| Seed demo data (docker) | `docker compose exec backend uv run python scripts/seed_demo.py` |
| Run backend locally | `cd backend && uv run uvicorn app.main:app --reload` |
| Run frontend locally | `cd frontend && npm run dev` |
| Backend tests | `cd backend && uv run pytest` |
| Frontend build/type-check | `cd frontend && npm run build` |
| Full reset | `docker compose down -v` |
| Deploy to a server | `./deploy/deploy.sh` (see DEPLOY.md) |
