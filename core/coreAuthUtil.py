# Core Auth Utilities

import bcrypt, jwt
from whenever import Instant, hours
from flask import request, jsonify
import os
from typing import Any, Callable
from main import logger

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")

def hash_password(password: str) -> str:
    logger.verbose("New Password hash generated!")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


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
            logger.verbose(f"User {user_id} successfully authenticated from {ip} | UA: {user_agent}")
            return func(data, *args, **kwargs)

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
