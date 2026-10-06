# Core Authentication Routes — v2

from flask import g, redirect, request, jsonify
from flask_openapi3 import APIBlueprint, Tag
from core.coreAuthUtil import AuthContext
from core.coreAuthUtil import (
    hash_password, check_password,
    create_session, refresh_session, revoke_session, revoke_all_sessions,
    invalidate_user_auth_cache, require_auth,
)
from core.database import db_helper
from core.logger import logger
from typing import cast, Any
import os, secrets, requests
from urllib.parse import urlencode
from core.coreCache import redis_client
from routes.auth_schemas import (
    AuthCodeBody, ChangePasswordBody, ChangePasswordResponse, DiscordCallbackQuery, DiscordExchangeResponse,
    ErrorResponse, LoginBody, LoginResponse, LogoutAllResponse, LogoutResponse,
    RegisterBody, RegisterResponse, SessionPath, SessionsResponse, SuccessResponse,
    TokenResponse,
)

bp = APIBlueprint(
    "auth",
    __name__,
    url_prefix="/api/auth",
    abp_tags=[Tag(name="Authentication", description="Account login, sessions, and Discord OAuth.")],
    abp_responses={401: ErrorResponse, 403: ErrorResponse},
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"


def _user_agent() -> str:
    return request.headers.get("User-Agent", "unknown")


# ---------------------------------------------------------------------------
# Manual Registration
# ---------------------------------------------------------------------------

@bp.post(
    "/register",
    summary="Register an account",
    description="Create a password-based account. Usernames and emails must be unique.",
    responses={201: RegisterResponse, 400: ErrorResponse, 409: ErrorResponse},
)
def register(body: RegisterBody):
    logger.verbose("Registering new user...")
    data = body.model_dump()
    username = data.get("username")
    email    = data.get("email")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Missing username or password"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters long"}), 400

    with db_helper.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
        if cur.fetchone():
            return jsonify({"error": "User already exists"}), 409

        cur.execute(
            "INSERT INTO users (uuid, username, email, password_hash, last_login, manual) "
            "VALUES (UUID(), %s, %s, %s, NOW(), TRUE)",
            (username, email, hash_password(password)),
        )

    logger.verbose(f"User registered: {username}")
    return jsonify({"success": True, "message": "Registered successfully!"}), 201


# ---------------------------------------------------------------------------
# Manual Login
# ---------------------------------------------------------------------------

@bp.post(
    "/login",
    summary="Log in",
    description="Verify account credentials and create a device session.",
    responses={200: LoginResponse},
)
def login(body: LoginBody):
    logger.verbose("Login API called...")
    data     = body.model_dump()
    email    = data.get("email")
    password = data.get("password")

    with db_helper.cursor() as cur:
        cur.execute(
            "SELECT id, password_hash, is_banned FROM users WHERE email=%s",
            (email,),
        )
        raw = cur.fetchone()
        user = cast(dict[str, Any], raw) if raw else None

        if not user:
            return jsonify({"error": "Invalid credentials"}), 401
        if user.get("is_banned"):
            return jsonify({"error": "This account has been banned"}), 403
        if user["password_hash"] is None:
            return jsonify({"error": "Invalid credentials"}), 401
        if not check_password(password, user["password_hash"]):
            return jsonify({"error": "Invalid credentials"}), 401

        cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user["id"],))

    device_name = data.get("device_name")  # optional friendly name from client
    session_id, token = create_session(
        user_id=user["id"],
        ip_address=_client_ip(),
        user_agent=_user_agent(),
        device_name=device_name,
    )

    logger.verbose(f"User {user['id']} logged in, session {session_id}")
    return jsonify({"token": token, "session_id": session_id})


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------

@bp.post(
    "/refresh",
    summary="Refresh a session token",
    description="Exchange a near-expiry session bearer token for a fresh token without creating another session.",
    security=[{"BearerAuth": []}],
    responses={200: TokenResponse},
)
def refresh():
    """
    Exchange a near-expiry session JWT for a fresh one.
    The session itself is NOT recreated — only a new short-lived JWT is signed.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid token"}), 401

    # We allow the decode to proceed even if expired (we use leeway)
    import jwt as _jwt
    token = auth_header.split(" ", 1)[1]
    try:
        payload = _jwt.decode(
            token,
            os.getenv("SECRET_KEY"),
            algorithms=["HS256"],
            options={"leeway": 60},   # allow up to 60 s past expiry for refresh
        )
    except _jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401

    session_id = payload.get("sid")
    if not session_id:
        return jsonify({"error": "Token missing session ID — please log in again"}), 401

    new_token = refresh_session(session_id, ip_address=_client_ip())
    if new_token is None:
        return jsonify({"error": "Session revoked or expired — please log in again"}), 401

    return jsonify({"token": new_token})


# ---------------------------------------------------------------------------
# Logout (current session)
# ---------------------------------------------------------------------------

@bp.post(
    "/logout",
    summary="Log out this session",
    description="Revoke the session associated with the supplied bearer token.",
    security=[{"BearerAuth": []}],
    responses={200: LogoutResponse},
)
@require_auth(inject_context=False)
def logout():
    ctx = cast(AuthContext, g.auth_context)
    if ctx.session_id:
        revoke_session(ctx.session_id)
        logger.verbose(f"User {ctx.user_id} logged out session {ctx.session_id}")
    return jsonify({"success": True, "message": "Logged out"})


# ---------------------------------------------------------------------------
# Logout all sessions
# ---------------------------------------------------------------------------

@bp.post(
    "/logout-all",
    summary="Log out all sessions",
    description="Revoke every active session belonging to the authenticated user.",
    security=[{"BearerAuth": []}],
    responses={200: LogoutAllResponse},
)
@require_auth(inject_context=False)
def logout_all():
    ctx = cast(AuthContext, g.auth_context)
    count = revoke_all_sessions(ctx.user_id)
    logger.verbose(f"User {ctx.user_id} logged out of all {count} sessions")
    return jsonify({"success": True, "sessions_revoked": count})


# ---------------------------------------------------------------------------
# List active sessions
# ---------------------------------------------------------------------------

@bp.get(
    "/sessions",
    summary="List active sessions",
    description="List the authenticated user's active sessions, marking the current session.",
    security=[{"BearerAuth": []}],
    responses={200: SessionsResponse},
)
@require_auth(inject_context=False)
def list_sessions():
    ctx = cast(AuthContext, g.auth_context)
    with db_helper.cursor() as cur:
        cur.execute(
            """
            SELECT id, created_at, last_used_at, expires_at,
                   ip_address, user_agent, device_name
            FROM user_sessions
            WHERE user_id = %s AND revoked = 0 AND expires_at > NOW()
            ORDER BY last_used_at DESC
            """,
            (ctx.user_id,),
        )
        rows = cur.fetchall()

    sessions = []
    for row in cast(list[dict[str, Any]], rows):
        sessions.append({
            "id":           row["id"],
            "created_at":   row["created_at"].isoformat() if row["created_at"] else None,
            "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
            "expires_at":   row["expires_at"].isoformat() if row["expires_at"] else None,
            "ip_address":   row["ip_address"],
            "device_name":  row["device_name"],
            "is_current":   row["id"] == ctx.session_id,
        })

    return jsonify({"sessions": sessions})


# ---------------------------------------------------------------------------
# Revoke specific session
# ---------------------------------------------------------------------------

@bp.delete(
    "/sessions/<string:session_id>",
    summary="Revoke a session",
    description="Revoke one of the authenticated user's sessions.",
    security=[{"BearerAuth": []}],
    responses={200: SuccessResponse, 404: ErrorResponse},
)
@require_auth(inject_context=False)
def delete_session(path: SessionPath):
    ctx = cast(AuthContext, g.auth_context)
    session_id = path.session_id
    # Confirm it belongs to this user before revoking
    with db_helper.cursor() as cur:
        cur.execute(
            "SELECT id FROM user_sessions WHERE id = %s AND user_id = %s",
            (session_id, ctx.user_id),
        )
        if not cur.fetchone():
            return jsonify({"error": "Session not found"}), 404

    revoke_session(session_id)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Change Password  (revokes all sessions, returns fresh token for current device)
# ---------------------------------------------------------------------------

@bp.post(
    "/change-password",
    summary="Change password",
    description="Change the account password, revoke existing sessions, and issue a replacement session token.",
    security=[{"BearerAuth": []}],
    responses={200: ChangePasswordResponse, 400: ErrorResponse, 404: ErrorResponse},
)
@require_auth(inject_context=False)
def change_password(body: ChangePasswordBody):
    ctx = cast(AuthContext, g.auth_context)
    req = body.model_dump()
    current_password = req.get("current_password")
    new_password     = req.get("new_password")
    device_name      = req.get("device_name")   # optional; re-names the new session

    logger.verbose(f"Password change request for user {ctx.user_id}")

    if not new_password or len(new_password) < 8:
        return jsonify({"error": "New password required (min 8 chars)"}), 400

    with db_helper.cursor() as cur:
        cur.execute(
            "SELECT password_hash FROM users WHERE id = %s",
            (ctx.user_id,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404

        user = cast(dict[str, Any], row)
        password_hash = user["password_hash"]

        if password_hash is not None:
            if not current_password:
                return jsonify({"error": "Current password is required"}), 400
            if not check_password(current_password, password_hash):
                return jsonify({"error": "Current password is incorrect"}), 401

        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(new_password), ctx.user_id),
        )

    # Revoke ALL sessions (security: old sessions are now invalid)
    revoke_all_sessions(ctx.user_id)
    invalidate_user_auth_cache(ctx.user_id)

    # Issue a fresh session for the current device so the user stays logged in
    _, new_token = create_session(
        user_id=ctx.user_id,
        ip_address=_client_ip(),
        user_agent=_user_agent(),
        device_name=device_name,
    )

    logger.verbose(f"Password changed for user {ctx.user_id}, all sessions revoked, new session issued")
    return jsonify({
        "success": True,
        "message": "Password updated. All other sessions have been logged out.",
        "token": new_token,
    })


# ---------------------------------------------------------------------------
# Discord OAuth2
# ---------------------------------------------------------------------------

CLIENT_ID        = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET    = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI     = os.getenv("DISCORD_REDIRECT_URI")
REDIRECT_URI_LINK = os.getenv("DISCORD_REDIRECT_URI_LINK")
BASE_URL         = os.getenv("FRONTEND_LINK")

_DISCORD_AUTH_CODE_TTL = 30   # seconds; one-time-use


@bp.get(
    "/discord",
    summary="Start Discord login",
    description="Redirect the browser to Discord OAuth to authenticate or register an account.",
    responses={302: {"description": "Redirect to Discord OAuth."}},
)
def discord_login():
    state = secrets.token_urlsafe(16)
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "identify email guilds guilds.members.read",
        "state":         state,
    }
    url = f"https://discord.com/oauth2/authorize?{urlencode(params)}"
    logger.verbose("New Discord login request...")
    resp = redirect(url)
    resp.set_cookie("discord_oauth_state", state, httponly=True, samesite="Lax", max_age=300)
    return resp


@bp.get(
    "/discord/link",
    summary="Start Discord account linking",
    description="Redirect the browser to Discord OAuth for account linking.",
    responses={302: {"description": "Redirect to Discord OAuth."}},
)
def discord_link():
    state = secrets.token_urlsafe(16)
    params = {
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "identify email guilds guilds.members.read",
        "state":         state,
    }
    url = f"https://discord.com/oauth2/authorize?{urlencode(params)}"
    logger.verbose("New Discord link request...")
    resp = redirect(url)
    resp.set_cookie("discord_oauth_state", state, httponly=True, samesite="Lax", max_age=300)
    return resp


@bp.get(
    "/discord/callback",
    summary="Complete Discord OAuth",
    description="Validate the OAuth state, exchange Discord's code, and redirect with a one-time auth code.",
    responses={
        302: {"description": "Redirect to the configured frontend."},
        401: ErrorResponse,
        403: ErrorResponse,
    },
)
def discord_callback(query: DiscordCallbackQuery):
    if BASE_URL is None:
        logger.error("BASE_URL missing in .env!")
        return redirect("http://brickrigs.de/login?err=500")

    # CSRF state check
    cookie_state = request.cookies.get("discord_oauth_state")
    req_state    = query.state
    if not cookie_state or not req_state or cookie_state != req_state:
        logger.warning("Discord login CSRF state mismatch!")
        return redirect(BASE_URL + "/login?err=403")

    code = query.code
    if not code:
        return redirect(BASE_URL + "/login?err=400")

    token_data = {
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "scope":         "identify email",
    }
    token_resp = requests.post(
        "https://discord.com/api/oauth2/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if token_resp.status_code != 200:
        logger.error(f"Discord token exchange failed: {token_resp.text}")
        return redirect(BASE_URL + "/login?err=401")

    access_token = token_resp.json()["access_token"]

    user_resp = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if user_resp.status_code != 200:
        return jsonify({"error": "Failed to fetch user data"}), 401

    discord_user = user_resp.json()
    if not discord_user:
        return redirect(BASE_URL + "/login?err=400")

    if not discord_user.get("verified", False):
        logger.warning(f"Unverified Discord email for {discord_user.get('username')}")
        return redirect(BASE_URL + "/login?err=403")

    discord_id  = discord_user["id"]
    email       = discord_user.get("email")
    username    = discord_user["username"]
    avatar_hash = discord_user.get("avatar")
    avatar_url  = (
        f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"
        if avatar_hash else None
    )

    if not email:
        logger.verbose(f"{username} did not grant email permission.")
        return redirect(BASE_URL + "/login?err=400")

    internal_user_id: int

    with db_helper.cursor() as cur:
        cur.execute("SELECT id, is_banned FROM users WHERE discord_id = %s", (discord_id,))
        raw_row = cur.fetchone()

        if raw_row is not None:
            row = cast(dict[str, Any], raw_row)
            if row.get("is_banned"):
                logger.warning(f"Banned user {row['id']} tried to login via Discord.")
                return redirect(BASE_URL + "/login?err=403")
            internal_user_id = int(row["id"])
        else:
            cur.execute("SELECT id, is_banned FROM users WHERE email = %s", (email,))
            existing = cur.fetchone()
            if existing:
                existing = cast(dict[str, Any], existing)
                if existing.get("is_banned"):
                    return redirect(BASE_URL + "/login?err=403")
                internal_user_id = int(existing["id"])
                cur.execute(
                    """
                    UPDATE users
                    SET discord_id = %s,
                        avatar_url = CASE
                            WHEN avatar_url IS NULL OR avatar_url = '' THEN %s
                            ELSE avatar_url
                        END
                    WHERE id = %s
                    """,
                    (discord_id, avatar_url, internal_user_id),
                )
            else:
                cur.execute(
                    "INSERT INTO users (uuid, username, email, discord_id, avatar_url, manual) "
                    "VALUES (UUID(), %s, %s, %s, %s, FALSE)",
                    (username, email, discord_id, avatar_url),
                )
                raw_id = cur.lastrowid
                if raw_id is None:
                    logger.error("Failed to retrieve last inserted ID")
                    return redirect(BASE_URL + "/login?err=500")
                internal_user_id = int(raw_id)

        cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (internal_user_id,))

    # Issue a session — but DON'T put the JWT in the URL.
    # Instead, store a one-time auth_code in Redis and redirect with that.
    session_id, jwt_token = create_session(
        user_id=internal_user_id,
        ip_address=_client_ip(),
        user_agent=_user_agent(),
        device_name="Discord OAuth",
    )

    auth_code = secrets.token_urlsafe(32)
    try:
        redis_client.setex(
            f"discord_auth_code:{auth_code}",
            _DISCORD_AUTH_CODE_TTL,
            jwt_token,
        )
    except Exception as e:
        logger.error(f"Failed to store Discord auth code in Redis: {e}")
        return redirect(BASE_URL + "/login?err=500")

    logger.verbose(f"Discord user {discord_id} → internal user {internal_user_id}, issuing auth_code")
    return redirect(BASE_URL + f"/dashboard?auth_code={auth_code}")


@bp.post(
    "/discord/exchange",
    summary="Exchange a Discord auth code",
    description="Consume a one-time Discord auth code and return its session token.",
    responses={200: DiscordExchangeResponse, 400: ErrorResponse, 401: ErrorResponse, 500: ErrorResponse},
)
def discord_exchange(body: AuthCodeBody):
    """
    Exchange the one-time auth_code (from the Discord callback redirect) for a JWT.
    The code is consumed immediately — re-use is rejected.
    """
    data = body.model_dump()
    auth_code = data.get("auth_code")
    if not auth_code:
        return jsonify({"error": "Missing auth_code"}), 400

    redis_key = f"discord_auth_code:{auth_code}"
    try:
        token = redis_client.get(redis_key)
        if token:
            redis_client.delete(redis_key)   # one-time use
    except Exception as e:
        logger.error(f"Redis error during auth_code exchange: {e}")
        return jsonify({"error": "Server error"}), 500

    if not token:
        return jsonify({"error": "Invalid or expired auth_code"}), 401

    logger.verbose("Discord auth_code exchanged successfully")
    return jsonify({"token": token})