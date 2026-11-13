# Linux deployment: hazivsroslyak.mooo.com

Requirements: Docker Engine with Compose v2, Git, DNS A record pointing to this server (remove a stale AAAA record), inbound TCP 80/443. Existing Nginx/Apache/Caddy must not occupy these ports. Do not stop another service without checking which sites it serves.

## Start

```bash
git clone --branch develop https://github.com/HaziVsroslyak/Smart_Kaspiy.git
cd Smart_Kaspiy
cp Docker/.env.example Docker/.env.production
# Optional: edit OPENWEATHER_API_KEY in Docker/.env.production.
sudo bash Docker/deploy.sh
sudo docker compose --env-file Docker/.env.production -f Docker/compose.production.yaml exec backend python -m scripts.bootstrap_root
curl --fail https://hazivsroslyak.mooo.com/healthz
```

Open https://hazivsroslyak.mooo.com and sign in using the root credentials entered interactively. No password is provided by the repository. Admin can create accounts after login. Only gateway publishes ports; API and frontend use a private network. Backend trusts forwarded headers only from the gateway's fixed IP. If subnet 172.30.11.0/24 is occupied, change subnet, gateway IP and FORWARDED_ALLOW_IPS together.

Certificate files default to `/etc/letsencrypt/live/hazivsroslyak.mooo.com/fullchain.pem` and `privkey.pem`. Mounting the entire directory preserves Certbot's links to `archive/`. Never commit certificates, private keys or `.env.production`. For the existing server certificate under `/root/cert/hazivsroslyak.mooo.com`, configure:

```dotenv
LETSENCRYPT_DIR=/root/cert
TLS_CERT_FILE=/etc/letsencrypt/hazivsroslyak.mooo.com/fullchain.pem
TLS_KEY_FILE=/etc/letsencrypt/hazivsroslyak.mooo.com/privkey.pem
HOST_CERT_FILE=/root/cert/hazivsroslyak.mooo.com/fullchain.pem
HOST_KEY_FILE=/root/cert/hazivsroslyak.mooo.com/privkey.pem
```

`TLS_*` paths are inside the container; `HOST_*` paths are checked by deploy.sh on Linux. Preserve any existing application checkout and deploy into a separate directory such as `/opt/smart-caspian-transit`.

## Renewal

The existing certificate remains managed by Certbot, not Caddy. Inspect `sudo certbot certificates` and the existing renewal method first. With ports 80/443 held by Caddy, use HTTP webroot or DNS renewal; standalone renewal cannot bind port 80 concurrently.

For HTTP webroot, prepare `sudo mkdir -p /var/www/certbot`, configure the certificate's renewal to use that webroot, then test with `sudo certbot renew --dry-run`. Caddy serves `/.well-known/acme-challenge/` on HTTP without redirect. After a successful renewal reload Caddy:

```bash
sudo bash /absolute/path/Smart_Kaspiy/Docker/reload-certificate.sh
```

Install this command as a Certbot deploy hook only after the path and dry-run work. For certificates managed automatically by Caddy instead, use `Caddyfile.online` and remove the explicit certificate mount/directive; preserve Caddy's data volume. Do not run two ACME clients for the same certificate without a deliberate renewal policy.

## Update and diagnostics

```bash
git pull --ff-only origin develop
sudo bash Docker/deploy.sh
sudo docker compose --env-file Docker/.env.production -f Docker/compose.production.yaml ps
sudo docker compose --env-file Docker/.env.production -f Docker/compose.production.yaml logs --tail=100 backend gateway
```

Updates create a consistent SQLite backup inside backend_data before replacing containers. Never use `down -v`: it deletes accounts, voyages and backups. Keep an off-server backup too. A fresh named volume receives ownership from the image; an existing incorrectly owned volume must be inspected and repaired for UID/GID 10001 before startup. Model training can delay the first launch for several minutes.
