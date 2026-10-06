# Auth V2 — Security Review, Design Rationale & Deployment Plan

## Security Review Results

### 🔴 Bugs Found & Fixed

| # | File | Issue | Fix |
|---|------|--------|-----|
| 1 | `coreAuthUtil.py` | API key embedded `user_id` in the raw key string (`sk_<id>_<random>`), leaking account identity to anyone who sees the key | Removed — format is now `sk_<64 random hex chars>` only |
| 2 | `coreAuthUtil.py` | `revoke_api_key()` deleted Redis key `apikey:{id}` but cache was stored under `apikey_hash:{hash}` — revoke never actually cleared the cache, so revoked keys kept working for up to 5 minutes | Fixed — now fetches the hash first, then deletes the correct cache key |
| 3 | `coreAuthUtil.py` | `expires_at` comparison used `<` against a real `datetime`, but when the key row came from Redis cache the value was a JSON-serialised `str` → would crash with `TypeError` on every cached API key hit | Fixed — normalises to `datetime` before comparing, handles both DB and Redis forms |
| 4 | `routes/Auth.py` | `change_password` called `request.get_json()` twice — once to get `current_password`/`new_password`, then again to get `device_name`. Flask drains the WSGI stream on first read; second call always returns `None` | Fixed — `device_name` pulled from the already-parsed `req` dict |

### ✅ Things That Are Correct

- **HMAC signing** — `HS256` with a server-held `SECRET_KEY` is fine. The key never leaves the server.
- **Session validation** — `revoked = 0 AND expires_at > NOW()` enforced in SQL, not just Redis, so revocation is immediate on cache miss.
- **User load** — `_load_user()` always checks `is_banned` before returning, so a ban takes effect within the 5-min Redis TTL.
- **Cross-user session revoke** — `DELETE /api/auth/sessions/<id>` confirms `user_id = ctx.user_id` before revoking.
- **Cross-user key revoke** — `revoke_api_key(key_id, user_id)` checks ownership in the UPDATE — `WHERE id=? AND user_id=?`.
- **API key storage** — only SHA-256 hash stored; raw key is returned once and discarded. DB breach exposes hashes that can't be reversed.
- **Discord auth_code** — one-time 30-second Redis key; JWT no longer appears in URL, browser history, server logs, or Referer headers.
- **Password change** — revokes all sessions including current one, then issues a fresh session so the user isn't logged out.
- **Backward compat** — `@require_token`, `@require_role`, `@require_permission` all still work; existing routes need zero changes.

---

## API Keys via `Authorization: Bearer` — Is It a Good Idea?

**Yes — this is the universal industry standard.**

| Service | Header used |
|---------|-------------|
| GitHub | `Authorization: Bearer ghp_...` |
| Stripe | `Authorization: Bearer sk_live_...` |
| OpenAI | `Authorization: Bearer sk-...` |
| Anthropic | `Authorization: Bearer sk-ant-...` |
| Cloudflare | `Authorization: Bearer <token>` |

The two alternatives are:
- `Authorization: Token <key>` — used by Django REST Framework, minor semantic difference, same security properties
- `X-API-Key: <key>` — used by some older APIs; the problem is it bypasses `Authorization` middleware that proxies, WAFs, and logging tools already know how to handle

**Bearer is the right choice.** Security comes from:
1. **HTTPS** — the header is encrypted in transit
2. **256-bit entropy** — `secrets.token_hex(32)` makes brute-force impossible
3. **Hash-only storage** — a DB breach doesn't expose the keys
4. **Revocation** — unlike the old JWTs, keys can be killed instantly

The `sk_` prefix makes it trivial to detect in logs and rotate if one leaks, which is the same reason GitHub prefixes their tokens.

---

## Deployment — Current State & What's Missing

### Current stack
```
git push → code is live immediately on next reload
start.sh reload → gunicorn SIGHUP → zero-downtime worker roll
```

### Problems
1. **No staging gate** — a bad commit goes straight to prod users
2. **No rollback mechanism** — you'd have to `git revert` and redeploy manually
3. **No DB migration gate** — schema changes could run before code, or vice versa
4. **Log level is `VERBOSE` in prod** — performance hit + potential data exposure

### Recommended approach for your setup (no CI/CD server)

Since you're running on a single Linux box with a systemd-adjacent screen session, the pragmatic path is a **two-branch + deploy script** model:

```
main ──────────────── always deployable, production code
dev  ──────────────── active work, agents commit here
```

**Deploy script** (`scripts/deploy.sh`):
```bash
#!/bin/bash
set -e
APP_DIR="/home/SilkC"
BACKUP_TAG=$(date +%Y%m%d_%H%M%S)

# 1. Tag current state for rollback
git -C $APP_DIR tag "rollback-$BACKUP_TAG" HEAD

# 2. Pull main
git -C $APP_DIR pull origin main

# 3. Run DB migrations (idempotent SQL with IF NOT EXISTS)
mysql -u $DB_USER -p$DB_PASS $DB_NAME < $APP_DIR/scripts/migrate_auth_v2.sql

# 4. Reload workers (zero-downtime)
MASTER_PID=$(pgrep -u silkc_user -o -f 'gunicorn.*main:app')
kill -HUP $MASTER_PID

echo "✅ Deployed. Rollback tag: rollback-$BACKUP_TAG"
echo "   To rollback: git -C $APP_DIR checkout rollback-$BACKUP_TAG && ./start.sh reload"
```

**config.yml log level** — change `log_level` to `QUIET` or `INFO` in production.

### Longer-term options (if the project grows)

| Option | Effort | Benefit |
|--------|--------|---------|
| GitHub Actions → deploy on PR merge to `main` | Low | Automated, auditable |
| Separate staging server | Medium | True isolation |
| Docker + blue-green swap | High | Instant rollback, zero-downtime schema changes |

---

## Documentation Plan

The most practical doc format for an API like this is an **OpenAPI 3.1 spec** — it generates interactive docs (Swagger UI / Redoc) automatically and can be used to generate client SDKs.

### Approach A — Static markdown (quick)
Write `docs/API.md` by hand. Good for small teams, becomes stale quickly.

### Approach B — `flask-openapi3` (recommended)
Replace the Blueprint decorators with `flask-openapi3` equivalents. The spec is generated automatically from type annotations. Adds:
- `/docs` — interactive Swagger UI
- `/openapi.json` — machine-readable spec

```python
# Before:
@bp.route("/login", methods=["POST"])
def login(): ...

# After (flask-openapi3):
from pydantic import BaseModel

class LoginBody(BaseModel):
    email: str
    password: str
    device_name: str | None = None

@bp.post("/login")
def login(body: LoginBody): ...
```

### Approach C — Manual OpenAPI YAML + Swagger UI static (middle ground)
Write `docs/openapi.yaml` by hand. Serve Swagger UI as a static route.
No code changes needed, survives refactors, but must be kept in sync manually.

### Endpoints to document (new auth surface)

```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/refresh
POST   /api/auth/logout
POST   /api/auth/logout-all
GET    /api/auth/sessions
DELETE /api/auth/sessions/{id}
POST   /api/auth/change-password
GET    /api/auth/discord
GET    /api/auth/discord/callback
POST   /api/auth/discord/exchange
GET    /api/keys
POST   /api/keys
DELETE /api/keys/{id}
PATCH  /api/keys/{id}
```
