# Personal Finance Statement Intelligence

Parses arbitrary bank statement exports (PDF or CSV, any bank, any layout) and
categorizes transactions through a cost-aware tiered pipeline — deterministic
parsing and rule/fuzzy-match categorization first, an LLM only as a batched,
last-resort fallback for low-confidence cases. See `docs/finance-master-prompt.md`
and `docs/finance-features.md` for the full spec this is being built against.

Being built phase by phase; architecture rationale and measured metrics will
be documented here as each phase lands.

## Stack

- Frontend: Next.js (TypeScript, Tailwind)
- Backend: FastAPI (Pydantic v2), Python, managed with `uv`
- Database: PostgreSQL
- Infra: Docker Compose, GitHub Actions

## Local development

Backend:

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

Full stack:

```bash
docker compose up --build
```

- Backend: http://localhost:8000/health
- Frontend: http://localhost:3000

## Tests

```bash
cd backend
uv run pytest
```
