#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file Docker/.env.production -f Docker/compose.production.yaml)
test -f Docker/.env.production || cp Docker/.env.example Docker/.env.production
"${compose[@]}" config --quiet
test -r /etc/letsencrypt/live/hazivsroslyak.mooo.com/fullchain.pem || {
  echo 'Missing certificate: /etc/letsencrypt/live/hazivsroslyak.mooo.com/fullchain.pem' >&2
  exit 1
}
test -r /etc/letsencrypt/live/hazivsroslyak.mooo.com/privkey.pem || {
  echo 'Missing certificate private key; run deployment with suitable permissions.' >&2
  exit 1
}
# SQLite backup API preserves a consistent snapshot even when WAL is active.
if "${compose[@]}" ps --status running --services | grep -qx backend; then
  "${compose[@]}" exec -T backend python -c 'import os,sqlite3,datetime; p=os.environ["DATABASE_PATH"]; name=p+".backup-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"); source=sqlite3.connect(p); target=sqlite3.connect(name); source.backup(target); target.close(); source.close(); print("SQLite backup created inside persistent volume")'
fi
"${compose[@]}" build
"${compose[@]}" up -d --wait --wait-timeout 600
"${compose[@]}" exec -T gateway caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
echo 'Ready: https://hazivsroslyak.mooo.com'
echo 'Create the first root: docker compose --env-file Docker/.env.production -f Docker/compose.production.yaml exec backend python -m scripts.bootstrap_root'
