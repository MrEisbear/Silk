# Core Auth Utilities — v2
#
# Changes from v1:
#   - JWTs are short-lived (15 min) and reference a session_id (`sid` claim).
#   - Sessions are stored in `user_sessions` and can be revoked individually or in bulk.
#   - API keys (hashed) are stored in `api_keys`; authenticated via "Bearer sk_..." header.
#   - Single unified decorator: @require_auth(role=..., permission=..., require_all=...)
#     which injects a typed AuthContext into every route.
#   - Legacy @require_token / @require_role / @require_permission kept as thin wrappers
#     so existing routes continue to work without changes.

import bcrypt, jwt, hashlib, re, os, secrets, uuid
import simplejson as json
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Optional, cast

from whenever import Instant, minutes, hours
from flask import g, request, jsonify
from core.coreCache import redis_client
from core.logger import logger


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")

PIN_SALT = os.getenv("PIN_SALT")
if not PIN_SALT:
    raise RuntimeError("PIN_SALT environment variable is required")

# JWT lifetime for session tokens (short — frontend refreshes automatically)
_JWT_TTL_MINUTES = 15

# How long a browser session stays alive after last use (rolling window)
_SESSION_TTL_HOURS = 24 * 30   # 30 days

# Redis TTL for session cache
_SESSION_CACHE_TTL = 300        # 5 min
_PERM_CACHE_TTL   = 600         # 10 min


# ---------------------------------------------------------------------------
# Password / PIN helpers  (unchanged from v1)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    logger.verbose("New Password hash generated!")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _pin_material(pin: str, uuid_str: str) -> bytes:
    data = f"{pin}:{uuid_str}:{PIN_SALT}".encode()
    return hashlib.sha256(data).digest()


def hash_pin(pin: str, uuid_str: str) -> str:
    logger.verbose("New PIN hash generated!")
    material = _pin_material(pin, uuid_str)
    return bcrypt.hashpw(material, bcrypt.gensalt()).decode()


def check_pin(pin: str, uuid_str: str, hashed: str | None) -> bool:
    if not hashed:
        logger.verbose("Pin Check failed, no Hashed Pin")
        return False
    material = _pin_material(pin, uuid_str)
    logger.verbose("A PIN got checked")
    return bcrypt.checkpw(material, hashed.encode())


def check_password(password: str, hashed: str) -> bool:
    logger.verbose("A password got checked")
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def create_session(user_id: int, ip_address: str | None = None,
                   user_agent: str | None = None,
                   device_name: str | None = None) -> tuple[str, str]:
    """
    Create a new user_session row and return (session_id, signed_jwt).
    The JWT contains only the session_id — no user data.
    """
    from core.database import db_helper
    session_id = str(uuid.uuid4())
    now = Instant.now()
    expires_at = now.add(hours=_SESSION_TTL_HOURS)

    with db_helper.cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_sessions
                (id, user_id, expires_at, ip_address, user_agent, device_name)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                session_id,
                user_id,
                expires_at.py_datetime(),
                ip_address,
                user_agent,
                device_name,
            ),
        )

    token = _sign_session_jwt(session_id)
    logger.verbose(f"Session {session_id} created for user {user_id}")
    return session_id, token


def _sign_session_jwt(session_id: str) -> str:
    now = Instant.now()
    payload = {
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int(now.add(minutes=_JWT_TTL_MINUTES).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def refresh_session(session_id: str, ip_address: str | None = None) -> str | None:
    """
    Validate that a session exists, is not revoked, and is not expired.
    Touching last_used_at and returning a fresh short-lived JWT.
    Returns None if the session is invalid/revoked/expired.
    """
    from core.database import db_helper
    from whenever import Instant

    now = Instant.now()
    with db_helper.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, revoked, expires_at
            FROM user_sessions WHERE id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    session = cast(dict[str, Any], row)
    if session["revoked"] or session["expires_at"] < now.py_datetime():
        return None

    # Touch last_used_at
    with db_helper.cursor() as cur:
        cur.execute(
            "UPDATE user_sessions SET last_used_at = NOW() WHERE id = %s",
            (session_id,),
        )

    return _sign_session_jwt(session_id)


def revoke_session(session_id: str) -> None:
    """Revoke a single session and clear its Redis cache."""
    from core.database import db_helper
    with db_helper.cursor() as cur:
        cur.execute(
            "UPDATE user_sessions SET revoked = 1 WHERE id = %s",
            (session_id,),
        )
    try:
        redis_client.delete(f"session:{session_id}")
    except Exception as e:
        logger.warning(f"Failed to clear Redis session cache for {session_id}: {e}")
    logger.verbose(f"Session {session_id} revoked")


def revoke_all_sessions(user_id: int) -> int:
    """Revoke every active session for a user. Returns the count revoked."""
    from core.database import db_helper
    with db_helper.cursor() as cur:
        cur.execute(
            "UPDATE user_sessions SET revoked = 1 WHERE user_id = %s AND revoked = 0",
            (user_id,),
        )
        count = cur.rowcount or 0

    invalidate_user_auth_cache(user_id)
    logger.verbose(f"Revoked {count} sessions for user {user_id}")
    return count


def invalidate_user_auth_cache(user_id: int | str) -> None:
    """Invalidates the Redis cache for a user (e.g. after ban or role change)."""
    try:
        redis_client.delete(f"auth_user:{user_id}")
        redis_client.delete(f"perm:{user_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate user auth cache for {user_id}: {e}")


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------

# Raw key format: silk_api_<64 random hex chars>
# The user_id is intentionally NOT embedded — it would reveal account identity
# to anyone who sees the key (logs, screenshots, shoulder-surfing).
_KEY_PREFIX = "silk_api"
_LEGACY_KEY_PREFIX = "sk"


def generate_api_key(user_id: int, name: str,
                     scope: list[str] | None = None,
                     expires_at: Any | None = None) -> tuple[int, str]:
    """
    Create a new API key row.
    Returns (api_key_id, raw_key).  The raw_key is shown ONCE to the user.
    """
    from core.database import db_helper

    random_part = secrets.token_hex(32)   # 64 hex chars = 256 bits of entropy
    raw_key     = f"{_KEY_PREFIX}_{random_part}"
    key_hash    = _hash_api_key(raw_key)
    key_prefix  = raw_key[:10]            # Fits api_keys.key_prefix and identifies Silk keys.

    with db_helper.cursor() as cur:
        cur.execute(
            """
            INSERT INTO api_keys (key_hash, key_prefix, user_id, name, expires_at, scope)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                key_hash,
                key_prefix,
                user_id,
                name,
                expires_at,
                json.dumps(scope) if scope is not None else None,
            ),
        )
        key_id = cur.lastrowid

    logger.verbose(f"API key '{name}' created for user {user_id} (id={key_id})")
    return key_id, raw_key


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def revoke_api_key(key_id: int, user_id: int) -> bool:
    """Revoke an API key. user_id is checked to prevent cross-user revocation."""
    from core.database import db_helper

    # Fetch key_hash before revoking so we can clear the correct Redis cache entry.
    # The cache is keyed by hash (not by id) since lookup happens by hash.
    key_hash_to_clear: str | None = None
    with db_helper.cursor() as cur:
        cur.execute(
            "SELECT key_hash FROM api_keys WHERE id = %s AND user_id = %s AND revoked = 0",
            (key_id, user_id),
        )
        row = cur.fetchone()
        if not row:
            return False
        key_hash_to_clear = cast(dict[str, Any], row)["key_hash"]

        cur.execute(
            "UPDATE api_keys SET revoked = 1 WHERE id = %s AND user_id = %s",
            (key_id, user_id),
        )
        affected = cur.rowcount or 0

    if affected and key_hash_to_clear:
        try:
            redis_client.delete(f"apikey_hash:{key_hash_to_clear}")
        except Exception:
            pass
    return bool(affected)


# ---------------------------------------------------------------------------
# AuthContext — the unified auth result injected into every route
# ---------------------------------------------------------------------------

@dataclass
class AuthContext:
    user_id:    int
    uuid:       str
    username:   str
    role:       Optional[str]
    is_banned:  bool
    session_id: Optional[str]     # None when authenticating via API key
    api_key_id: Optional[int]     # None when authenticating via session JWT
    _permissions: Optional[set[str]] = field(default=None, repr=False)

    # ----- Permission helpers -----

    @property
    def permissions(self) -> set[str]:
        if self._permissions is None:
            self._permissions = get_user_permissions(self.user_id)
        return self._permissions

    def has_permission(self, key: str) -> bool:
        # When authenticated via a scoped API key, also check the key's scope
        if self.api_key_id is not None and self._api_key_scope is not None:
            if not has_permission(set(self._api_key_scope), key):
                return False
        return has_permission(self.permissions, key)

    def check_role(self, required: str) -> bool:
        if required == "admin":
            return self.role == "admin"
        if required == "mod":
            return self.role in ("admin", "mod")
        return True

    # Internal — populated by _resolve_api_key_auth when key is scoped
    _api_key_scope: Optional[list[str]] = field(default=None, repr=False)

    def to_legacy_dict(self) -> dict[str, Any]:
        """Back-compat shim so old routes that do data['id'] still work."""
        return {
            "id":       self.user_id,
            "uuid":     self.uuid,
            "username": self.username,
            "role":     self.role,
            "is_banned": self.is_banned,
        }


# ---------------------------------------------------------------------------
# Internal auth resolvers
# ---------------------------------------------------------------------------

def _resolve_session_auth(token: str) -> AuthContext | None:
    """Validate a session JWT, look up the session, look up the user."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.verbose("Session JWT expired")
        return None
    except jwt.InvalidTokenError:
        logger.verbose("Session JWT invalid")
        return None

    session_id = payload.get("sid")
    if not session_id:
        return None

    # Redis cache for session → user_id mapping
    cache_key = f"session:{session_id}"
    user_id: int | None = None
    try:
        cached = redis_client.get(cache_key)
        if cached:
            user_id = int(cached)
    except Exception as e:
        logger.warning(f"Redis session cache read error: {e}")

    if user_id is None:
        from core.database import db_helper
        with db_helper.cursor() as cur:
            cur.execute(
                """
                SELECT user_id FROM user_sessions
                WHERE id = %s AND revoked = 0 AND expires_at > NOW()
                """,
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            logger.verbose(f"Session {session_id} not found or revoked")
            return None

        sess = cast(dict[str, Any], row)
        user_id = int(sess["user_id"])

        # Touch last_used_at (fire-and-forget via second query)
        try:
            from core.database import db_helper as _db
            with _db.cursor() as cur:
                cur.execute(
                    "UPDATE user_sessions SET last_used_at = NOW() WHERE id = %s",
                    (session_id,),
                )
        except Exception:
            pass

        try:
            redis_client.setex(cache_key, _SESSION_CACHE_TTL, str(user_id))
        except Exception as e:
            logger.warning(f"Redis session cache write error: {e}")

    user = _load_user(user_id)
    if user is None:
        return None

    return AuthContext(
        user_id=user["id"],
        uuid=user["uuid"],
        username=user["username"],
        role=user["role"],
        is_banned=bool(user["is_banned"]),
        session_id=session_id,
        api_key_id=None,
    )


def _resolve_api_key_auth(raw_key: str) -> AuthContext | None:
    """Validate a raw API key, look up the key row, look up the user."""
    key_hash = _hash_api_key(raw_key)

    # Try Redis cache first
    cache_key = f"apikey_hash:{key_hash}"
    key_row: dict[str, Any] | None = None
    try:
        cached = redis_client.get(cache_key)
        if cached:
            key_row = json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis API key cache read error: {e}")

    if key_row is None:
        from core.database import db_helper
        with db_helper.cursor() as cur:
            cur.execute(
                """
                SELECT id, user_id, revoked, expires_at, scope
                FROM api_keys
                WHERE key_hash = %s
                """,
                (key_hash,),
            )
            row = cur.fetchone()

        if not row:
            return None

        key_row = cast(dict[str, Any], row)

        try:
            redis_client.setex(cache_key, _SESSION_CACHE_TTL, json.dumps(key_row))
        except Exception as e:
            logger.warning(f"Redis API key cache write error: {e}")

    if key_row["revoked"]:
        logger.verbose(f"API key {key_row['id']} is revoked")
        return None

    # expires_at may be a datetime (from DB) or a string (from Redis JSON cache).
    # Normalise to datetime before comparing.
    raw_expires = key_row.get("expires_at")
    if raw_expires is not None:
        from datetime import datetime as _dt, timezone as _tz
        if isinstance(raw_expires, str):
            try:
                raw_expires = _dt.fromisoformat(raw_expires.replace("Z", "+00:00"))
            except ValueError:
                raw_expires = None
        if raw_expires is not None:
            now_naive = _dt.utcnow()
            expires_naive = (
                raw_expires.replace(tzinfo=None)
                if raw_expires.tzinfo is not None
                else raw_expires
            )
            if expires_naive < now_naive:
                logger.verbose(f"API key {key_row['id']} has expired")
                return None

    # Update last_used_at asynchronously (best-effort)
    try:
        from core.database import db_helper as _db
        with _db.cursor() as cur:
            cur.execute(
                "UPDATE api_keys SET last_used_at = NOW() WHERE id = %s",
                (key_row["id"],),
            )
    except Exception:
        pass

    user = _load_user(int(key_row["user_id"]))
    if user is None:
        return None

    scope_raw = key_row.get("scope")
    scope: list[str] | None = None
    if scope_raw is not None:
        scope = json.loads(scope_raw) if isinstance(scope_raw, str) else scope_raw

    ctx = AuthContext(
        user_id=user["id"],
        uuid=user["uuid"],
        username=user["username"],
        role=user["role"],
        is_banned=bool(user["is_banned"]),
        session_id=None,
        api_key_id=int(key_row["id"]),
        _api_key_scope=scope,
    )
    return ctx


def _load_user(user_id: int) -> dict[str, Any] | None:
    """Load user from Redis cache or DB. Returns None if banned or not found."""
    cache_key = f"auth_user:{user_id}"
    user: dict[str, Any] | None = None

    try:
        cached = redis_client.get(cache_key)
        if cached:
            user = json.loads(str(cached))
    except Exception as e:
        logger.warning(f"Redis user cache read error: {e}")

    if not user:
        from core.database import db_session
        from models import User
        with db_session() as session:
            user_obj = session.get(User, user_id)
            if not user_obj:
                logger.verbose(f"User {user_id} not found in DB")
                return None
            user = {
                "id":       user_obj.id,
                "uuid":     user_obj.uuid,
                "role":     user_obj.role,
                "is_banned": user_obj.is_banned,
                "username": user_obj.username,
            }
        try:
            redis_client.setex(cache_key, _SESSION_CACHE_TTL, json.dumps(user))
        except Exception as e:
            logger.warning(f"Redis user cache write error: {e}")

    if user.get("is_banned"):
        logger.warning(f"Banned user {user_id} attempted access")
        return None

    return user


def _is_api_key(token: str) -> bool:
    """Return True if the Bearer token looks like an API key (starts with 'sk_').

    Design note: API keys are sent in the standard Authorization: Bearer header,
    the same as session JWTs. This is the universal industry convention (GitHub,
    Stripe, OpenAI all do this). The project-specific prefix lets us route keys
    to the correct resolver without a separate header. HTTPS protects the token
    in transit; the SHA-256 hash stored in DB protects keys in a database breach.
    """
    return token.startswith((f"{_KEY_PREFIX}_", f"{_LEGACY_KEY_PREFIX}_"))


# ---------------------------------------------------------------------------
# Primary decorator: @require_auth
# ---------------------------------------------------------------------------

def require_auth(
    role: str | None = None,
    permission: str | None = None,
    permissions: tuple[str, ...] = (),
    require_all: bool = False,
    allow_api_key: bool = True,
    inject_context: bool = True,
):
    """
    Unified authentication + authorisation decorator.

    Usage:
        @require_auth()                             # any logged-in user
        @require_auth(role="admin")                 # admin only
        @require_auth(permission="payments.send")   # single permission
        @require_auth(permissions=("a","b"), require_all=True)

    The decorated function receives an AuthContext as its first argument.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            ua = request.headers.get("User-Agent", "unknown")

            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                logger.verbose(f"Missing/invalid auth header from {ip}")
                return jsonify({"error": "Missing or invalid token"}), 401

            token = auth_header.split(" ", 1)[1]

            if allow_api_key and _is_api_key(token):
                ctx = _resolve_api_key_auth(token)
                if ctx is None:
                    return jsonify({"error": "Invalid or revoked API key"}), 401
            else:
                ctx = _resolve_session_auth(token)
                if ctx is None:
                    return jsonify({"error": "Invalid, expired, or revoked session"}), 401

            if ctx.is_banned:
                return jsonify({"error": "Account is banned"}), 403

            # Role check
            if role is not None and not ctx.check_role(role):
                logger.warning(
                    f"Access denied for user {ctx.user_id} "
                    f"(role: {ctx.role}) — required: {role}"
                )
                return jsonify({"error": f"Forbidden: {role} access required"}), 403

            # Permission check
            all_permissions = permissions + ((permission,) if permission else ())
            if all_permissions:
                if require_all:
                    ok = all(ctx.has_permission(p) for p in all_permissions)
                else:
                    ok = any(ctx.has_permission(p) for p in all_permissions)
                if not ok:
                    return jsonify({"error": "Missing required permissions"}), 403

            logger.verbose(
                f"User {ctx.user_id} authenticated from {ip} | UA: {ua}"
            )
            if inject_context:
                return func(ctx, *args, **kwargs)
            g.auth_context = ctx
            return func(*args, **kwargs)

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Legacy shims (keep existing routes working with zero changes)
# ---------------------------------------------------------------------------

def require_token(func: Callable[..., Any]) -> Callable[..., Any]:
    """Legacy decorator — wraps require_auth() and converts AuthContext to dict."""
    @wraps(func)
    @require_auth()
    def wrapper(ctx: AuthContext, *args: Any, **kwargs: Any) -> Any:
        return func(ctx.to_legacy_dict(), *args, **kwargs)
    return wrapper


def require_role(required_role: str) -> Callable[..., Any]:
    """Legacy decorator."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        @require_auth(role=required_role)
        def wrapper(ctx: AuthContext, *args: Any, **kwargs: Any) -> Any:
            return func(ctx.to_legacy_dict(), *args, **kwargs)
        return wrapper
    return decorator


def require_permission(*permission_keys: str, require_all: bool = False):
    """Legacy decorator."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        @require_auth(permissions=permission_keys, require_all=require_all)
        def wrapper(ctx: AuthContext, *args: Any, **kwargs: Any) -> Any:
            return func(ctx.to_legacy_dict(), *args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Permission engine  (unchanged from v1)
# ---------------------------------------------------------------------------

def compile_pattern(pattern: str) -> re.Pattern[str]:
    """
    Converts permission pattern into regex.
    Supports:
    - ** (matches across dot segments)
    - *  (matches within a single dot segment)
    """
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*\*", ".*")
    escaped = escaped.replace(r"\*", r"[^.]+")
    return re.compile("^" + escaped + "$")


def match_permission(pattern: str, required: str) -> bool:
    return compile_pattern(pattern).match(required) is not None


def has_permission(user_permissions: set[str], required: str) -> bool:
    best_allow = -1
    best_deny  = -1

    def score(p: str) -> int:
        return p.count("*") * -10 + len(p)

    for perm in user_permissions:
        is_deny = perm.startswith("!")
        clean   = perm[1:] if is_deny else perm

        if not match_permission(clean, required):
            continue

        s = score(clean)
        if is_deny:
            best_deny  = max(best_deny, s)
        else:
            best_allow = max(best_allow, s)

    if best_allow == -1 and best_deny == -1:
        return False
    if best_deny > best_allow:
        return False
    if best_allow > best_deny:
        return True
    return best_allow != -1 and best_deny == -1


def get_user_permissions(user_id: int) -> set[str]:
    cache_key  = f"perm:{user_id}"
    cached_raw = redis_client.get(cache_key)

    if cached_raw is not None:
        cached_str: str = cast(str, cached_raw)
        return set(cast(list[str], json.loads(cached_str)))

    from core.database import db_helper

    with db_helper.cursor() as cur:
        cur.execute("""
        WITH RECURSIVE job_tree AS (
            SELECT uj.job_id
            FROM user_jobs uj
            WHERE uj.user_uuid = (SELECT uuid FROM users WHERE id = %s)

            UNION ALL

            SELECT j.parent_job_id
            FROM jobs j
            JOIN job_tree jt ON j.id = jt.job_id
            WHERE j.parent_job_id IS NOT NULL
        ),

        job_perms AS (
            SELECT p.permission_key
            FROM permissions p
            JOIN job_permissions jp ON jp.permission_id = p.id
            WHERE jp.job_id IN (SELECT job_id FROM job_tree)
        ),

        user_perms AS (
            SELECT p.permission_key
            FROM permissions p
            JOIN user_permissions up ON up.permission_id = p.id
            WHERE up.user_uuid = (SELECT uuid FROM users WHERE id = %s)
        ),

        group_perms AS (
            SELECT p.permission_key
            FROM permissions p
            JOIN group_permissions gp ON gp.permission_id = p.id
            JOIN user_groups ug ON ug.group_id = gp.group_id
            WHERE ug.user_uuid = (SELECT uuid FROM users WHERE id = %s)

            UNION

            SELECT p.permission_key
            FROM permissions p
            JOIN group_permissions gp ON gp.permission_id = p.id
            JOIN permission_groups pg ON pg.id = gp.group_id
            WHERE pg.group_key = 'default'
        )

        SELECT permission_key FROM job_perms
        UNION
        SELECT permission_key FROM user_perms
        UNION
        SELECT permission_key FROM group_perms
        """, (user_id, user_id, user_id))

        rows = cast(list[dict[str, Any]], cur.fetchall())
        permissions = {r["permission_key"] for r in rows}

    redis_client.setex(cache_key, _PERM_CACHE_TTL, json.dumps(list(permissions)))
    return permissions


# ---------------------------------------------------------------------------
# Legacy JWT creator  (kept for reference; no longer used for new sessions)
# ---------------------------------------------------------------------------

def create_jwt(user_id: int) -> str:
    """
    DEPRECATED — creates old-style bare JWTs with 30-day expiry.
    Use create_session() instead for new code.
    Kept only so scripts/tooling that import it don't break.
    """
    logger.verbose(f"[DEPRECATED] create_jwt called for {user_id}")
    now = Instant.now()
    payload = {
        "id":  user_id,
        "iat": int(now.timestamp()),
        "exp": int(now.add(hours=24 * 30).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")
