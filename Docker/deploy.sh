#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose --env-file Docker/.env.production -f Docker/compose.production.yaml)
test -f Docker/.env.production || cp Docker/.env.example Docker/.env.production
# Only read the two preflight paths; never source executable shell from an env file.
env_path() {
  local key="$1" fallback="$2" value
  value=$(sed -n "s/^${key}=//p" Docker/.env.production | tail -n 1 | tr -d '\r')
  printf '%s' "${value:-$fallback}"
}
host_cert=$(env_path HOST_CERT_FILE /etc/letsencrypt/live/hazivsroslyak.mooo.com/fullchain.pem)
host_key=$(env_path HOST_KEY_FILE /etc/letsencrypt/live/hazivsroslyak.mooo.com/privkey.pem)
"${compose[@]}" config --quiet
test -r "$host_cert" || {
  echo "Missing certificate: $host_cert" >&2
  exit 1
}
test -r "$host_key" || {
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
