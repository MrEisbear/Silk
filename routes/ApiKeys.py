# API Key Management Routes

from flask import g, jsonify
from flask_openapi3 import APIBlueprint, Tag
from core.coreAuthUtil import (
    AuthContext, generate_api_key, require_auth, revoke_api_key,
)
from core.database import db_helper
from core.coreCache import redis_client
from core.logger import logger
from typing import cast, Any
from routes.auth_schemas import (
    ErrorResponse, KeyCreateBody, KeyCreateResponse, KeyPath, KeysResponse,
    KeyUpdateBody, SuccessResponse,
)

bp = APIBlueprint(
    "api_keys",
    __name__,
    url_prefix="/api/keys",
    abp_tags=[Tag(name="API keys", description="Create, inspect, and revoke programmatic API keys.")],
    abp_responses={401: ErrorResponse, 403: ErrorResponse},
)


@bp.get(
    "",
    summary="List API keys",
    description="List active API keys belonging to the authenticated user. Raw keys are never returned.",
    security=[{"BearerAuth": []}],
    responses={200: KeysResponse},
)
@require_auth(inject_context=False)
def list_keys():
    ctx = cast(AuthContext, g.auth_context)
    """List all API keys for the authenticated user."""
    with db_helper.cursor() as cur:
        cur.execute(
            """
            SELECT id, key_prefix, name, created_at, last_used_at, expires_at,
                   revoked, scope
            FROM api_keys
            WHERE user_id = %s AND revoked = 0
            ORDER BY created_at DESC
            """,
            (ctx.user_id,),
        )
        rows = cur.fetchall()

    keys = []
    for row in cast(list[dict[str, Any]], rows):
        keys.append({
            "id":           row["id"],
            "key_prefix":   row["key_prefix"],
            "name":         row["name"],
            "created_at":   row["created_at"].isoformat() if row["created_at"] else None,
            "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
            "expires_at":   row["expires_at"].isoformat() if row["expires_at"] else None,
            "scope":        row["scope"],   # None = full access
        })

    return jsonify({"keys": keys})


@bp.post(
    "",
    summary="Create an API key",
    description="Create a Silk API key. The raw key is returned once and is not stored; save it immediately.",
    security=[{"BearerAuth": []}],
    responses={201: KeyCreateResponse, 400: ErrorResponse},
)
@require_auth(inject_context=False)
def create_key(body: KeyCreateBody):
    """
    Create a new API key.
    The raw key is returned ONCE and never stored — save it immediately.

    Body:
      name        string   required
      scope       [str]    optional list of permission_key strings (null = full)
      expires_at  string   optional ISO datetime (null = never)
    """
    ctx = cast(AuthContext, g.auth_context)
    data = body.model_dump()

    name = data.get("name", "").strip()
    if not name or len(name) > 128:
        return jsonify({"error": "name is required (max 128 chars)"}), 400

    scope: list[str] | None = data.get("scope")   # None or list of strings
    if scope is not None:
        if not isinstance(scope, list) or not all(isinstance(s, str) for s in scope):
            return jsonify({"error": "scope must be a list of permission key strings"}), 400
        if len(scope) > 200:
            return jsonify({"error": "scope too large (max 200 permissions)"}), 400

    expires_at = None
    expires_raw = data.get("expires_at")
    if expires_raw:
        from datetime import datetime
        try:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "expires_at must be a valid ISO 8601 datetime"}), 400

    key_id, raw_key = generate_api_key(
        user_id=ctx.user_id,
        name=name,
        scope=scope,
        expires_at=expires_at,
    )

    logger.verbose(f"API key '{name}' created for user {ctx.user_id}")
    return jsonify({
        "id":      key_id,
        "key":     raw_key,   # ⚠️ shown ONCE — store it now
        "name":    name,
        "scope":   scope,
        "message": "Store this key — it will not be shown again.",
    }), 201


@bp.delete(
    "/<int:key_id>",
    summary="Revoke an API key",
    description="Revoke an active API key owned by the authenticated user.",
    security=[{"BearerAuth": []}],
    responses={200: SuccessResponse, 404: ErrorResponse},
)
@require_auth(inject_context=False)
def delete_key(path: KeyPath):
    """Revoke an API key. Only the owning user can do this."""
    ctx = cast(AuthContext, g.auth_context)
    key_id = path.key_id
    success = revoke_api_key(key_id, ctx.user_id)
    if not success:
        return jsonify({"error": "Key not found or already revoked"}), 404

    logger.verbose(f"API key {key_id} revoked by user {ctx.user_id}")
    return jsonify({"success": True})


@bp.patch(
    "/<int:key_id>",
    summary="Update an API key",
    description="Update the name or permission scope of an active API key owned by the authenticated user.",
    security=[{"BearerAuth": []}],
    responses={200: SuccessResponse, 400: ErrorResponse, 404: ErrorResponse},
)
@require_auth(inject_context=False)
def update_key(path: KeyPath, body: KeyUpdateBody):
    """
    Update a key's name or scope.

    Body (all optional):
      name   string
      scope  [str] | null    null = reset to full user permissions
    """
    ctx = cast(AuthContext, g.auth_context)
    key_id = path.key_id
    data = body.model_dump(exclude_unset=True)
    updates = []
    params: list[Any] = []

    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 128:
            return jsonify({"error": "name must be 1–128 chars"}), 400
        updates.append("name = %s")
        params.append(name)

    if "scope" in data:
        scope = data["scope"]
        if scope is None:
            updates.append("scope = NULL")
        elif isinstance(scope, list) and all(isinstance(s, str) for s in scope):
            import json as _json
            updates.append("scope = %s")
            params.append(_json.dumps(scope))
        else:
            return jsonify({"error": "scope must be a list of strings or null"}), 400

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    params += [key_id, ctx.user_id]

    with db_helper.cursor() as cur:
        cur.execute(
            "SELECT key_hash FROM api_keys WHERE id = %s AND user_id = %s AND revoked = 0",
            (key_id, ctx.user_id),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Key not found"}), 404
        key_hash = cast(dict[str, Any], row)["key_hash"]

        query = f"UPDATE api_keys SET {', '.join(updates)} WHERE id = %s AND user_id = %s AND revoked = 0"
        cur.execute(query, params)
        if not cur.rowcount:
            return jsonify({"error": "Key not found"}), 404

    redis_client.delete(f"apikey_hash:{key_hash}")

    return jsonify({"success": True})
