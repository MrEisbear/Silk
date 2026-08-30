import os
from flask import Blueprint, request, jsonify
import requests
from core.coreAuthUtil import require_token, get_user_permissions
from core.database import db_helper
from core.logger import logger
from typing import cast, Any
from urllib.parse import urlparse

bp = Blueprint("user", __name__, url_prefix="/api")

@bp.route("/me/permissions", methods=["GET"])
@require_token
def me_permissions(data):
    user_id = data["id"]
    perms = get_user_permissions(user_id)
    return jsonify({"permissions": list(perms)})

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
        user = cast(dict[str, Any], row)
        logger.verbose(f"Information retrieved from {user_id}")
        return jsonify({
            "uuid": user["uuid"],
            "username": user["username"],
            "email": user["email"],
            "discord_id": user["discord_id"],
            "avatar": user["avatar_url"],
            "created": user["created_at"],
            "verified": user["is_verified"],
            "public_leaderboard": user["public_leaderboard"]
        })

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
@bp.route("/me/discord-avatar", methods=["POST"])
@require_token
def copy_discord_avatar(data):
    user_id = data["id"]
    with db_helper.cursor() as cur:
        cur.execute("SELECT discord_id FROM users WHERE id = %s", (user_id,))
        user = cast(dict[str, Any], cur.fetchone())
        if not user:
            logger.verbose("User not found; 404")
            return {"success": False, "message": "User not found"}, 404
        if not user["discord_id"]:
            logger.verbose("User not linked to discord; 400")
            return {"success": False, "message": "User not linked to discord"}, 400
        discord_id: int = cast(int, user["discord_id"])
        response = requests.get(
            url=f"https://discord.com/api/v10/users/{discord_id}",
            headers={
                "Authorization": f"Bot {BOT_TOKEN}"
            },
            timeout=10,
        )
        if response.status_code != 200:
            logger.error(f"Failed to fetch avatar from discord: {response.status_code} {response.text}")
            return {"success": False, "message": "Failed to fetch avatar"}, 500
        user_data = response.json()
        if not user_data.get("avatar"):
            logger.verbose("User not linked to discord; 400")
            return {"success": False, "message": "User not linked to discord"}, 400
        avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{user_data['avatar']}.png"
        cur.execute("UPDATE users SET avatar_url = %s WHERE id = %s", (avatar_url, user_id))
        logger.verbose(f"Avatar updated for user {user_id}")
        return {"success": True, "message": "Avatar updated"}, 200


@bp.route("/settings/leaderboard-visibility", methods=["PATCH"])
@require_token
def update_leaderboard_visibility(data: dict[str, int | str | bool]):
    # Extract authenticated user ID
    user_id: int | None = cast(int | None, data.get("id"))
    if not user_id:
        return {"error": "Unauthorized"}, 401

    # Parse incoming JSON payload
    req_data = request.get_json(silent=True) or {}
    
    if "public_leaderboard" not in req_data:
        return {"error": "Missing 'public_leaderboard' boolean in request body"}, 400
        
    # Convert to standard boolean, then to 1/0 for MySQL tinyint
    is_public = bool(req_data["public_leaderboard"])
    status_int = 1 if is_public else 0

    with db_helper.cursor() as cur:
        # Update the user's preference
        cur.execute("""
            UPDATE users 
            SET public_leaderboard = %s 
            WHERE id = %s
        """, (status_int, user_id))
        
        # Note: Depending on your db_helper implementation, you may need to 
        # explicitly call a commit method here if it doesn't auto-commit on exit.
        # e.g., cur.connection.commit()
        
    return {
        "success": True, 
        "public_leaderboard": is_public
    }, 200

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

@bp.route("/user/<uuid:user_uuid>", methods=["GET"])
def public_profile(user_uuid):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    with db_helper.cursor() as cur:
        cur.execute("SELECT username, avatar_url, created_at, discord_id, uuid, id FROM users WHERE uuid = %s AND is_banned = 0", (str(user_uuid),))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404
        user = cast(dict[str, Any], row)
        logger.verbose(f"user {user['username']} requested from {ip}")
        return jsonify({
            "uuid": str(user_uuid),
            "id": user["id"],
            "username": user["username"],
            "avatar_url": user["avatar_url"],
            "created_at": user["created_at"].isoformat() if user["created_at"] else None,
            "discord_id": user["discord_id"]
        })

@bp.route("/user/<string:userid>", methods=["GET"])
def public_profile_id(userid):
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    with db_helper.cursor() as cur:
        cur.execute("SELECT username, avatar_url, created_at, uuid, discord_id FROM users WHERE id = %s AND is_banned = 0", (str(userid),))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404
        user = cast(dict[str, Any], row)
        logger.verbose(f"user {user['username']} requested from {ip}")
        return jsonify({
            "uuid": str(user["uuid"]),
            "username": user["username"],
            "avatar_url": user["avatar_url"],
            "created_at": user["created_at"].isoformat() if user["created_at"] else None,
            "discord_id": user["discord_id"]
        })