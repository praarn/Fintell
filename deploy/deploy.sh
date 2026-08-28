#!/usr/bin/env bash
# Build + (re)start the production stack. Safe to re-run for every deploy —
# migrations run on backend start; data lives in named volumes.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env.prod ]]; then
  echo "error: .env.prod not found. Copy .env.prod.example to .env.prod and fill it in." >&2
  exit 1
fi

COMPOSE=(docker compose --env-file .env.prod -f docker-compose.prod.yml)

# Pull latest source if this is a git checkout on a branch.
if git rev-parse --abbrev-ref HEAD >/dev/null 2>&1; then
  git pull --ff-only || echo "warning: git pull skipped/failed; deploying working tree as-is"
fi

"${COMPOSE[@]}" up -d --build
"${COMPOSE[@]}" ps
echo
echo "Deployed. Tail logs with:"
echo "  docker compose --env-file .env.prod -f docker-compose.prod.yml logs -f"
