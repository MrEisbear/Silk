# Core Authentication

from flask import Blueprint, redirect, request, jsonify
from core.coreAuthUtil import hash_password, check_password, create_jwt, require_token
from core.database import db_helper
from core.logger import logger
from typing import cast, Dict, Any
import os
import requests
from urllib.parse import urlencode

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# Manual Registering
@bp.route("/register", methods=["POST"])
def register():
    logger.verbose("Registering new user...")
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not password:
        logger.verbose("Register failed due to missing data; 400")
        return jsonify({"error": "Missing username or password"}), 400
    if len(password) < 8:
        logger.verbose("Register failed due to password length; 400")
        return jsonify({"error": "Password must be at least 8 characters long"}), 400
    with db_helper.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
        if cur.fetchone():
            logger.verbose("Register failed due to existing user; 409")
            return jsonify({"error": "User already exists"}), 409

        cur.execute("""
            INSERT INTO users (uuid, username, email, password_hash, manual)
            VALUES (UUID(), %s, %s, %s, TRUE)
        """, (username, email, hash_password(password)))
    
    logger.verbose(f"User sucessfully registered! {username}")
    return jsonify({"success": True, "message": "Registered successfully!"}), 201

# Manual Authentication
@bp.route("/login", methods=["POST"])
def login():
    logger.verbose("Login API called...")
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    with db_helper.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE email=%s", (email,))
        raw = cur.fetchone()
        user = cast(Dict[str, Any], raw) if raw else None

        if not user or not check_password(password, user["password_hash"]):
            logger.verbose("Login failed due to invalid credentials; 401")
            return jsonify({"error": "Invalid credentials"}), 401

        token = create_jwt(user["id"])
        logger.verbose("Logged user with id " + str(user["id"]) + "in!")
    return jsonify({"token": token})

# Discord Authentication
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
REDIRECT_URI_LINK = os.getenv("DISCORD_REDIRECT_URI_LINK")


@bp.route("/discord", methods=["POST"])
def discord_login():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "identify email guilds guilds.members.read",
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    logger.verbose("New Discord login request...")
    return redirect(url)

@bp.route("/discord/link", methods=["POST"])
def discord_link():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI_LINK,
        "response_type": "code",
        "scope": "identify guilds guilds.members.read",
    }
    url = f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    logger.verbose("New Discord link request...")
    return redirect(url)

@bp.route("/discord/callback")
def discord_callback():
    logger.verbose("Recieved discord call back...")
    code = request.args.get("code")
    if not code:
        logger.verbose("Discord callback had no auth code")
        return jsonify({"error": "No authorization code provided"}), 400
    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "scope": "identify email",
    }
    token_headers = {"Content-Type": "application/x-www-form-urlencoded"}

    token_resp = requests.post(
        "https://discord.com/api/oauth2/token",
        data=token_data,
        headers=token_headers,
        timeout=10,
    )
    if token_resp.status_code != 200:
        logger.error(f"Discord token exchange failed: {token_resp.text}")
        return jsonify({"error": "Authentication failed"}), 401

    access_token = token_resp.json()["access_token"]

    user_resp = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if user_resp.status_code != 200:
        logger.error(f"Failed to fetch Discord user: {user_resp.text}")
        return jsonify({"error": "Failed to fetch user data"}), 401

    discord_user = user_resp.json()
    discord_id = discord_user["id"]
    email = discord_user.get("email")
    username = discord_user["username"]
    internal_user_id: int
    if email == None:
        logger.verbose(f"{username} did not grand email permission, callback denied.")
        return jsonify({"error": "Email permission not granted"}), 400
    with db_helper.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE discord_id = %s", (discord_id,))
        raw_row = cur.fetchone()

        if raw_row is not None:
            row = cast(Dict[str, Any], raw_row)
            try:
                internal_user_id = int(row["id"])
            except (ValueError, TypeError, KeyError):
                logger.error(f"Invalid user ID in DB for discord_id={discord_id}: {row}")
                return jsonify({"error": "Internal server error"}), 500
        else:
            # Insert new user
            cur.execute("SELECT id FROM users WHERE email = %s", (email))
            exists = cur.fetchone()
            if exists:
                logger.verbose(f"User with email {email} already exists")
                return jsonify({"error": "User already exists"}), 409
            cur.execute("""
                INSERT INTO users (uuid, username, email, discord_id, manual)
                VALUES (UUID(), %s, %s, %s, FALSE)
            """, (username, email, discord_id))
            raw_id = cur.lastrowid
            if raw_id is None:
                logger.error("Failed to retrieve last inserted ID")
                return jsonify({"error": "Internal server error"}), 500
            internal_user_id: int = int(raw_id)

    # Issue JWT
    token = create_jwt(internal_user_id)
    logger.verbose(f"Discord user {discord_id} authenticated as internal user {internal_user_id}")
    return jsonify({"token": token})

@bp.route("/change-password", methods=["POST"])
@require_token
def change_password(data):
    user_id = data["id"]
    req = request.get_json()
    current_password = req.get("current_password")
    new_password = req.get("new_password")
    logger.verbose("New Password change request!")
    if not new_password or len(new_password) < 8:
        logger.verbose("Password not changed due to length; 400")
        return jsonify({"error": "New password required (min 8 chars)"}), 400

    with db_helper.cursor() as cur:
        cur.execute("SELECT password_hash, manual FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            logger.verbose("Password not changed due to missing user; 404")
            return jsonify({"error": "User not found"}), 404

        user = cast(Dict[str, Any], row)
        password_hash = user["password_hash"]
        is_manual = bool(user["manual"])

        # If user has a password, require current password
        if password_hash is not None:
            if not current_password:
                logger.verbose("Password not changed due to missing password; 404")
                return jsonify({"error": "Current password is required"}), 400
            if not check_password(current_password, password_hash):
                logger.verbose("Password not changed due to invalid password; 401")
                return jsonify({"error": "Current password is incorrect"}), 401

        # Update password
        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(new_password), user_id)
        )
    logger.verbose(f"Password updated for user {user_id}")
    return jsonify({"success": True, "message": "Password updated"})

@bp.route("/discord/link-call", methods=["POST"])
@require_token
def link_discord(data):
    user_id = data["id"]
    req = request.get_json()
    discord_code = req.get("code")

    if not discord_code:
        logger.verbose("Discord link failed due to missing code; 400")
        return jsonify({"error": "Authorization code required"}), 400

    # Exchange code for token (same as callback)
    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": discord_code,
        "redirect_uri": REDIRECT_URI_LINK,
        "scope": "identify guilds guilds.members.read",
    }
    token_resp = requests.post(
        "https://discord.com/api/oauth2/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if token_resp.status_code != 200:
        logger.verbose("Discord link failed due to invalid code; 400")
        return jsonify({"error": "Invalid Discord code"}), 400

    access_token = token_resp.json()["access_token"]

    # Get Discord user
    user_resp = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if user_resp.status_code != 200:
        logger.verbose("Discord link failed due could not fetch Discord profile; 400")
        return jsonify({"error": "Could not fetch Discord profile"}), 400

    discord_user = user_resp.json()
    discord_id = discord_user["id"]

    # Ensure this Discord account isn't already linked
    with db_helper.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE discord_id = %s", (discord_id,))
        if cur.fetchone():
            logger.verbose("Discord link failed due to already linked discord account; 400")
            return jsonify({"error": "This Discord account is already linked"}), 409
        cur.execute("SELECT discord_id FROM users WHERE id = %s", (user_id,))
        if cur.fetchone():
            logger.verbose("Discord link failed due to already linked account; 400")
            return jsonify({"error": "This account is already linked"}), 409

        # Link to current user
        cur.execute(
            "UPDATE users SET discord_id = %s WHERE id = %s",
            (discord_id, user_id)
        )

    logger.verbose(f"User {user_id} linked Discord ID {discord_id}")
    return jsonify({"success": True, "message": "Discord account linked"})