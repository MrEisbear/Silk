# Core Auth Utilities

import bcrypt, jwt
from core.coreCache import redis_client
import simplejson as json
from whenever import Instant, hours
from flask import request, jsonify
import os
from typing import Any, Callable, cast
from core.logger import logger
import hashlib
import re
from functools import wraps

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")
PIN_SALT = os.getenv("PIN_SALT")
if not PIN_SALT:
    raise RuntimeError("PIN_SALT environment variable is required")

def hash_password(password: str) -> str:
    logger.verbose("New Password hash generated!")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def _pin_material(pin: str, uuid: str) -> bytes:
    data = f"{pin}:{uuid}:{PIN_SALT}".encode()
    return hashlib.sha256(data).digest()

def hash_pin(pin: str, uuid: str) -> str:
    logger.verbose("New PIN hash generated!")
    material = _pin_material(pin, uuid)
    return bcrypt.hashpw(material, bcrypt.gensalt()).decode()

def check_pin(pin: str, uuid: str, hashed: str | None) -> bool:
    if not hashed:
        logger.verbose("Pin Check failed, no Hashed Pin")
        return False
    material = _pin_material(pin, uuid)
    logger.verbose("A PIN got checked")
    return bcrypt.checkpw(material, hashed.encode())

def check_password(password: str, hashed: str) -> bool:
    logger.verbose("A password got checked")
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_jwt(user_id: int) -> str:
    logger.verbose(f"JWT Created for {user_id}")
    now = Instant.now()
    payload = {
        "id": user_id,
        "iat": int(now.timestamp()),
        "exp": int(now.add(hours=24*30).timestamp())
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def require_token(func: Callable[..., Any]) -> Callable[..., Any]:
    from functools import wraps
    import jwt

    @wraps(func)
    def wrapper(*args, **kwargs):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        user_agent = request.headers.get("User-Agent", "unknown")

        logger.verbose(f"Authentication check started from {ip} | UA: {user_agent}")

        auth = request.headers.get("Authorization")
        if not auth or not auth.startswith("Bearer "):
            logger.verbose(f"Missing/invalid auth header from {ip} | UA: {user_agent}")
            return jsonify({"error": "Missing or invalid token"}), 401

        token = auth.split(" ", 1)[1]

        # Try to extract user_id from token for logging—even if invalid/expired
        unverified_user_id = "unknown"
        try:
            # ⚠️ DO NOT use this payload for auth logic—only for logging!
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            unverified_user_id = unverified_payload.get("id", "missing")
        except Exception:
            pass  # keep as "unknown"

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user_id = data.get("id", "unknown")

            # Validate against DB (Check Ban Status & Update Role)
            from core.database import db_helper
            with db_helper.cursor() as cur:
                # We check for is_banned AND fetch role/username to optimize downstream calls
                cur.execute("SELECT id, role, is_banned, username FROM users WHERE id = %s", (user_id,))
                # Cast to dict because generic stubs don't know about dictionary=True
                user = cast(dict[str, Any] | None, cur.fetchone())

                if not user:
                    logger.verbose(f"Token valid but user {user_id} not found in DB")
                    return jsonify({"error": "User not found"}), 401

                if user.get("is_banned"):
                    logger.warning(f"Banned user {user_id} attempted access")
                    return jsonify({"error": "Account is banned"}), 403

                # Merge DB data into token data for efficient role checking
                # Token data has 'iat', 'exp'; DB has 'role', 'is_banned', etc.
                # DB data overrides token data if collision (unlikely except 'id')
                user_data = dict(data)
                user_data.update(user) 

            logger.verbose(f"User {user_id} successfully authenticated from {ip} | UA: {user_agent}")
            return func(user_data, *args, **kwargs)

        except jwt.ExpiredSignatureError:
            logger.verbose(
                f"Expired token from {ip} | UA: {user_agent} | user_id: {unverified_user_id}"
            )
            return jsonify({"error": "Token expired"}), 401

        except jwt.InvalidTokenError:
            logger.verbose(
                f"Invalid token from {ip} | UA: {user_agent} | user_id: {unverified_user_id}"
            )
            return jsonify({"error": "Invalid token"}), 401
    return wrapper



def compile_pattern(pattern: str) -> re.Pattern[str]:
    """
    Converts permission pattern into regex.
    Supports:   
    - ** (matches across dot segments)
    - * (matches within a single dot segment)
    - prefix, suffix, middle wildcards
    """

    escaped = re.escape(pattern)

    # restore wildcard meaning
    # A double asterisk `\*\*` becomes `.*` (match across dots)
    escaped = escaped.replace(r"\*\*", ".*")
    # A single asterisk `\*` becomes `[^.]+` (match anything except a dot)
    escaped = escaped.replace(r"\*", r"[^.]+")

    # anchor full match
    return re.compile("^" + escaped + "$")


def match_permission(pattern: str, required: str) -> bool:
    return compile_pattern(pattern).match(required) is not None


def has_permission(user_permissions: set[str], required: str) -> bool:
    best_allow = -1
    best_deny = -1

    def score(pattern: str) -> int:
        # specificity = fewer wildcards = more specific
        return pattern.count("*") * -10 + len(pattern)

    for perm in user_permissions:
        is_deny = perm.startswith("!")
        clean = perm[1:] if is_deny else perm

        if not match_permission(clean, required):
            continue

        s = score(clean)

        if is_deny:
            best_deny = max(best_deny, s)
        else:
            best_allow = max(best_allow, s)

    if best_allow == -1 and best_deny == -1:
        return False

    if best_deny > best_allow:
        return False
    if best_allow > best_deny:
        return True

    return best_allow != -1 and best_deny == -1


def require_permission(permission_key: str):
    from functools import wraps

    def decorator(func):
        @wraps(func)
        @require_token
        def wrapper(data, *args, **kwargs):
            user_id = data.get("id")
            if not user_id:
                return jsonify({"error": f"Missing permission: {permission_key}"}), 403

            cache_key = f"perm:{user_id}"

            cached_raw = redis_client.get(cache_key)

            if cached_raw is not None:
                cached_str: str = cast(str, cached_raw)
                permissions = set(cast(list[str], json.loads(cached_str)))

            else:
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

                redis_client.setex(cache_key, 600, json.dumps(list(permissions)))

            if not has_permission(permissions, permission_key):
                return jsonify({"error": f"Missing permission: {permission_key}"}), 403
            return func(data, *args, **kwargs)
        return wrapper
    return decorator

def require_role(required_role: str) -> Callable[..., Any]:
    """
    Decorator to require a specific role ('admin' or 'mod').
    - 'admin' requires role='admin'.
    - 'mod' requires role='mod' OR 'admin'.
    """
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        @require_token # Use existing token check first (which now populates role!)
        def wrapper(data, *args, **kwargs):
            user_id = data.get("id")
            if not user_id:
                return jsonify({"error": "Unauthorized"}), 401
            
            # Role should be populated by require_token, but fallback if needed
            user_role = data.get("role")
            
            if user_role is None:
                # Fallback to DB check (only happens if require_token didn't do its job or logic changed)
                from core.database import db_helper
                with db_helper.cursor() as cur:
                    cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
                    row = cast(dict[str, Any] | None, cur.fetchone())
                    if not row:
                         return jsonify({"error": "User not found"}), 404
                    user_role = row.get("role", "user")

            # Normalize role
            if not user_role: 
                user_role = "user"
            
            if required_role == "admin":
                if user_role != "admin":
                    logger.warning(f"Access denied for user {user_id} (role: {user_role}) to admin resource")
                    return jsonify({"error": "Forbidden: Admin access required"}), 403
                    
            elif required_role == "mod":
                if user_role not in ["admin", "mod"]:
                    logger.warning(f"Access denied for user {user_id} (role: {user_role}) to mod resource")
                    return jsonify({"error": "Forbidden: Moderator access required"}), 403
                        
            return func(data, *args, **kwargs)
        return wrapper
    return decorator
