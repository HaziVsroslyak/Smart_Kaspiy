#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --env-file Docker/.env.production -f Docker/compose.production.yaml exec -T gateway \
  caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile --force
