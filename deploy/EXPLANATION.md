# deploy/ — explanation

Everything needed to run the production stack on a single Linux server with
Docker. The step-by-step runbook is the root [`DEPLOY.md`](../DEPLOY.md);
this file explains what each piece does and why.

## Files

| File | Role |
| --- | --- |
| `../docker-compose.prod.yml` | the production stack definition |
| `Caddyfile` | reverse-proxy + automatic HTTPS config |
| `deploy.sh` | build + migrate + (re)start; safe to re-run every deploy |
| `../.env.prod.example` | secrets template → copy to `../.env.prod` (gitignored) |

## Topology

```
browser ──HTTPS──▶ caddy (:80/:443, the only published ports)
                     ├── /        ─▶ frontend  :3000   (Next.js `next start`)
                     └── /api/*   ─▶ backend   :8000   (FastAPI; prefix stripped)
                                        │
                                   postgres :5432      (internal only)
volumes: postgres_data · backend_uploads · caddy_data · caddy_config
```

## Why it's shaped this way

- **One domain, `/api` prefix.** Caddy's `handle_path /api/*` strips the
  prefix before forwarding, so the browser and API share an origin and
  there is **no CORS** to configure and **one** TLS cert to manage.
- **Caddy does TLS automatically.** On first start it obtains a Let's
  Encrypt certificate for `$DOMAIN` (the server must be reachable on 80
  and 443, and DNS must already point at it). Certs persist in the
  `caddy_data` volume.
- **Backend migrates on start.** Its `command` runs `alembic upgrade head`
  before `uvicorn`, so a deploy never needs a separate migration step.
- **Frontend API URL is baked at build time.** `docker-compose.prod.yml`
  passes `NEXT_PUBLIC_API_BASE_URL=https://$DOMAIN/api` as a build arg;
  changing `DOMAIN` means rebuilding (`./deploy/deploy.sh` does that).
- **Nothing but Caddy is exposed.** Postgres and the two app services are
  only reachable on the internal compose network.
- **State is in named volumes.** `postgres_data` (the database) and
  `backend_uploads` (raw statement files) survive `down`/`up` and image
  rebuilds. Back them up (see `DEPLOY.md` → Backups).

## Deploy

```bash
cp .env.prod.example .env.prod   # then edit: DOMAIN, POSTGRES_PASSWORD, JWT_SECRET_KEY
./deploy/deploy.sh
```
