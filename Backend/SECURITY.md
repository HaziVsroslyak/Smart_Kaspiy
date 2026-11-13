# Security deployment

Passwords use Argon2id. Session identifiers are random opaque values; SQLite stores digests. Cookies require HTTPS (`Secure`, `HttpOnly`, `SameSite=Lax`). All mutations require an allowed Origin and CSRF header. Login starts with GET `/api/v1/auth/csrf`.

Initialize root through `python -m scripts.bootstrap_root` from Backend; the command prompts for credentials. No default account/password is shipped. Existing voyages remain root-only until assigned. Back up SQLite before upgrading. Never restore an old anonymous API against the upgraded database.

Docker uses one HTTPS origin at https://localhost. Run `docker compose -f Docker/compose.yaml up --build -d`; initialize root inside backend using the bootstrap command. Install the local Caddy root certificate into the client trust store before logging in; do not disable TLS verification. The certificate is in Caddy's persistent data volume at `/data/caddy/pki/authorities/local/root.crt`. Copy only this certificate, never the CA private key. Backend and frontend ports are internal.

Internet deployment requires a domain, a public listener and `Caddyfile.online`, plus APP_ORIGINS matching the exact HTTPS origin. Local internal CA does not create a publicly trusted certificate. Docker execution must be checked on a host with Docker installed.

Admin may create logisticians, reset their password and freeze their accounts. Root controls roles, unfreezing and voyage transfer. Reset passwords are shown once and require changing before business access. Freeze/reset revokes sessions. Administrative events are recorded without password/session values.

This slice does not include deletion requests or final account deletion. The agreed next slice implements transfer-before-delete and retained audit history.
