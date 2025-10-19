from flask import Blueprint, redirect, request, jsonify
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from typing import cast, Dict, Any
import os
import requests
from urllib.parse import urlencode, urlparse

bp = Blueprint("user", __name__, url_prefix="/api")

@bp.route("/me", methods=["GET"])
@require_token
def me(data):
    user_id = data["id"]
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s",(user_id,))
        row = cur.fetchone()
        if not row:
            logger.verbose("User not found; 404")
            return jsonify({"error": "User not found"}), 404
        user = cast(Dict[str, Any], row)
        logger.verbose(f"Information retrieved from {user_id}")
        return jsonify({
            "uuid": user["uuid"],
            "username": user["username"],
            "email": user["email"],
            "discord_id": user["discord_id"],
            "avatar": user["avatar_url"],
            "created": user["created_at"],
            "verified": user["is_verified"]
        })

@bp.route("/me", methods=["PATCH"])
@require_token
def update_me(data):
    user_id = data["id"]
    req = request.get_json()
    if not isinstance(req, dict):
        return jsonify({"error": "Invalid JSON"}), 400
    logger.verbose(f"Profile being updated of {user_id}...")
    updates = []
    params = []

    # Validate and add username
    if "username" in req:
        username = req["username"]
        if not isinstance(username, str) or not (1 <= len(username.strip()) <= 16):
            return jsonify({"error": "Username must be a non-empty string (1–16 chars)"}), 400
        updates.append("username = %s")
        params.append(username.strip())

    # Validate and add avatar_url
    if "avatar_url" in req:
        url = req["avatar_url"]
        if url is None:
            updates.append("avatar_url = NULL")
            # no param needed for NULL
        elif isinstance(url, str) and is_valid_url(url):
            updates.append("avatar_url = %s")
            params.append(url.strip())
        else:
            return jsonify({"error": "Invalid avatar URL"}), 400

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    params.append(user_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"

    with db_helper.cursor() as cur:
        cur.execute(query, params)
    logger.verbose(f"Profile updated for user {user_id}")
    return jsonify({"success": True, "message": "Profile updated"})


def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False

@bp.route("/user/<uuid:user_uuid>")
def public_profile(user_uuid):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    with db_helper.cursor() as cur:
        cur.execute("SELECT username, avatar_url, created_at FROM users WHERE uuid = %s AND is_banned = 0", (str(user_uuid),))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404
        user = cast(Dict[str, Any], row)
        logger.verbose(f"user {user['username']} requested from {ip}")
        return jsonify({
            "uuid": str(user_uuid),
            "username": user["username"],
            "avatar_url": user["avatar_url"],
            "created_at": user["created_at"].isoformat() if user["created_at"] else None,
            "discord_id": user["discord_id"]
        })