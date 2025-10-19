from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from typing import Dict, Any, cast
import os

bp = Blueprint("accounting", __name__, url_prefix="/api/bank")


@bp.route("/accounts", methods=["GET"])
@require_token
def get_user_accounts(data):
    user_id = data["id"]
    logger.verbose(f"Retrieving bank accounts of {user_id}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM bank_accounts WHERE account_holder_id  = %s and account_holder_type = 'user'", (user_id,))
        rows = cur.fetchall()
        # The cursor already returns dict-like rows, so `dict(row)` is not needed.
        return jsonify({"accounts": rows})

@bp.route("/accounts", methods=["POST"])
@require_token
def create_user_accounts(data):
    user_id = data["id"]
    logger.verbose(f"Creating bank accounts for {user_id}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        user = cast(Dict[str, Any], row)
        discord_id = user["discord_id"]
        if discord_id == None:
            type = "M-"
            discord_id = user_id
        else:
            type = "D-"
        cur.execute("SELECT * FROM bank_accounts WHERE account_number = %s", (type + str(discord_id),))
        row = cur.fetchone()
        if row:
            type = "S-"
            accnum = type + os.urandom(4).hex()
        else:
            accnum = type + str(discord_id)
        cur.execute("SELECT * FROM bank_accounts WHERE account_number = %s", (accnum,))
        row = cur.fetchone()
        if row:
            logger.verbose(f"Failed to create Bank Account for {user_id}. attempted accnum = {accnum}")
            return jsonify({"error": "Failed to create bank account"}), 500
        cur.execute("INSERT INTO bank_accounts (account_number, account_holder_type, account_holder_id) VALUES (%s, %s, %s)", (accnum, 'user', user_id,))
    logger.verbose(f"Bank Account created for {user_id}; {accnum}")
    return jsonify({"account_number": accnum}), 201

@bp.route("/accounts/<uuid:account_uuid>", methods=["GET"])
@require_token
def retrieve_acc_details(data, account_uuid):
    user_id = data["id"]
    account_uuid = str(account_uuid)
    logger.verbose(f"Retrieving bank account {account_uuid}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM bank_accounts WHERE uuid = %s", (account_uuid,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        account = cast(Dict[str, Any], row)
        if account["account_holder_id"] != user_id:
            return jsonify({"error": "Account not found"}), 404
        return jsonify({
            "balance": account["balance"],
            "account_number": account["account_number"],
            "created_at": account["created_at"].isoformat() if account["created_at"] else None,
            "updated_at": account["updated_at"].isoformat() if account["updated_at"] else None,
            "is_frozen": account["is_frozen"]
            })

@bp.route("/accounts/<uuid:account_uuid>", methods=["PATCH"])
@require_token
def update_acc_details(data, account_uuid):
    user_id = data["id"]
    account_uuid = str(account_uuid)
    req = request.get_json()
    freeze = req.get("is_frozen")
    if freeze is not isinstance(freeze, bool):
        return jsonify({"error": "Invalid JSON"}), 400
    logger.verbose(f"Updating bank account {account_uuid}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM bank_accounts WHERE uuid = %s", (account_uuid,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        account = cast(Dict[str, Any], row)
        if account["account_holder_id"] != user_id:
            return jsonify({"error": "Account not found"}), 404
        cur.execute("UPDATE bank_accounts SET is_frozen = %s WHERE uuid = %s", (freeze, account_uuid))
    return jsonify({"success": True, "message": "Account updated"})

# Public Acc lookup
@bp.route("/public/<uuid:account_uuid>", methods=["PATCH"])
@require_token
def lookup_uuid(data, account_uuid):
    logger.verbose(f"Retrieving balance from {account_uuid}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT balance, is_frozen FROM bank_accounts WHERE uuid = %s", (account_uuid,))
        row = cur.fetchone()
        account = cast(Dict[str, Any], row)
        if not row or account["is_frozen"]:
            return jsonify({"error": "Account not found"})
    return jsonify({
        "balance": account["balance"]
    })

@bp.route("/public/<accnum:accnum>", methods=["PATCH"])
@require_token
def lookup_accnum(data, accnum):
    
    with db_helper.cursor() as cur:
        cur.execute("SELECT balance, is_frozen, uuid FROM bank_accounts WHERE account_number  = %s", (accnum,))
        row = cur.fetchone()
        account = cast(Dict[str, Any], row)
        if not row or account["is_frozen"]:
            return jsonify({"error": "Account not found"})
    logger.verbose(f"Retrieving balance from {account['uuid']}...")
    return jsonify({
        "balance": account["balance"],
        "uuid": account["uuid"]
    })

