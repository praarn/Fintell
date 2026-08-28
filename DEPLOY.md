# Deploying Fintell (VPS + Docker Compose)

Runs the whole stack — Postgres, the FastAPI backend, the Next.js frontend,
and a Caddy reverse proxy that terminates TLS — on a single server you
control. Caddy serves the app at `https://<your-domain>/` and proxies
`https://<your-domain>/api/*` to the backend, so there is no CORS to
configure and only one certificate to manage.

```
                         ┌──────────── your server ────────────┐
  browser ──HTTPS──▶ caddy :80/:443                            │
                         ├── /        ─▶ frontend :3000 (Next) │
                         └── /api/*   ─▶ backend  :8000 (API)  │
                                            │                  │
                                       postgres :5432          │
                         └─────────────────────────────────────┘
```

---

## 1. Prerequisites (you provide)

- A Linux server (1 vCPU / 2 GB RAM is enough for a demo) with:
  - **Docker Engine** + the **Compose v2** plugin
    (`docker compose version` should work)
  - ports **80** and **443** open to the internet
- A **domain name** with an `A` (and/or `AAAA`) record pointing at the
  server's public IP. Certificate issuance fails until DNS resolves.

Everything below runs **on the server**.

## 2. Get the code

```bash
git clone https://github.com/praarn/Fintell.git
cd Fintell
```

## 3. Configure secrets

```bash
cp .env.prod.example .env.prod
```

Edit `.env.prod`:

| Variable | What to set |
| --- | --- |
| `DOMAIN` | your domain, e.g. `fintell.example.com` (no scheme, no trailing slash) |
| `POSTGRES_PASSWORD` | a strong random value — `openssl rand -base64 24` |
| `JWT_SECRET_KEY` | a long random value — `openssl rand -hex 48` |
| `LLM_API_KEY` | optional; set it to enable Tier 3 categorization + "Ask your finances" |

`.env.prod` is gitignored. Keep it on the server only.

## 4. Deploy

```bash
./deploy/deploy.sh
```

This builds the images, applies database migrations (the backend runs
`alembic upgrade head` on start), and brings everything up. First run also
triggers Caddy to obtain a Let's Encrypt certificate — give it a minute,
then open `https://<your-domain>/`.

## 5. Create the first user

Register through the UI at `https://<your-domain>/register`.

Optionally load the synthetic demo data (`demo@fintell.app` /
`demo-password-123`, six months of generated multi-bank history):

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  exec backend uv run python scripts/seed_merchant_lookup.py
docker compose --env-file .env.prod -f docker-compose.prod.yml \
  exec backend uv run python scripts/seed_demo.py
```

---

## Operating it

All commands use the same prefix; export it once per shell if you like:

```bash
alias dc='docker compose --env-file .env.prod -f docker-compose.prod.yml'
```

| Task | Command |
| --- | --- |
| Update to latest `main` | `./deploy/deploy.sh` |
| Status | `dc ps` |
| Logs (all) | `dc logs -f` |
| Logs (one service) | `dc logs -f backend` |
| Restart one service | `dc restart backend` |
| Stop everything | `dc down` |
| Shell in the backend | `dc exec backend sh` |
| Run a migration by hand | `dc exec backend uv run alembic upgrade head` |

### Backups

The database and uploaded statement files live in the named volumes
`postgres_data` and `backend_uploads`.

```bash
# database dump
dc exec -T postgres pg_dump -U finance finance | gzip > fintell-$(date +%F).sql.gz

# restore
gunzip -c fintell-2026-01-01.sql.gz | dc exec -T postgres psql -U finance finance
```

Copy the dumps off the server (another host, object storage) on a schedule.

### Troubleshooting

- **`password authentication failed for user "finance"`** — Postgres only
  applies `POSTGRES_PASSWORD` when it *initialises* an empty data
  directory. If you changed the password after the first deploy, the
  `postgres_data` volume still has the old one. Either set it back, or
  change it in-place: `dc exec postgres psql -U finance -c "ALTER USER
  finance PASSWORD 'new-one';"` and update `.env.prod` to match.
- **Certificate not issued** — Caddy needs the domain's DNS to resolve to
  this server *and* inbound 80/443 open before Let's Encrypt will
  validate. Check `dc logs caddy`.
- **Port 80/443 already in use** — another web server (nginx, Apache, a
  stray container) is bound. Stop it; only Caddy should hold those ports.

### Notes & limitations

- **Uploaded files** are stored on disk in the `backend_uploads` volume —
  fine for a single server, not replicated. Object storage is the next
  step if you scale out.
- **Rate-limit and anomaly-suppression state are in-process**, so they
  reset on a backend restart.
- The frontend's API URL (`https://<DOMAIN>/api`) is **baked in at image
  build time**. If you change `DOMAIN`, rebuild: `./deploy/deploy.sh`.
- Postgres is **not** published to the host — reach it only via
  `dc exec postgres ...`.
