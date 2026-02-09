from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token, hash_pin
from core.database import db_helper
from core.logger import logger
from typing import Dict, Any, cast
import os
from core.coreRandUtil import generate_account_number


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
            try:
                accnum = generate_account_number(type, cur)
            except RuntimeError:
                logger.error(f"Failed to generate account number for {user_id}, see brickrigs.de/api/docs/gen for Help.")
                return jsonify({"error": "Failed to generate account number"}), 500
        else:
            accnum = type + str(discord_id)
        cur.execute("SELECT * FROM bank_accounts WHERE account_number = %s", (accnum,))
        row = cur.fetchone()
        if row:
            logger.error(f"Failed to create Bank Account for {user_id}. attempted accnum = {accnum}")
            return jsonify({"error": "Failed to create bank account"}), 500
        try:
            cur.execute("INSERT INTO bank_accounts (account_number, account_holder_type, account_holder_id) VALUES (%s, %s, %s)", (accnum, 'user', user_id,))
        except Exception as e:
            logger.error(e)
            return jsonify({"error": "Failed to create bank account"}), 500
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
        if int(account["account_holder_id"]) != user_id:
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
    if freeze:
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
    pin = str(req.get("pin"))
    if len(pin) not in [4, 5, 6]:
        return jsonify({"error": "Invalid JSON"}), 400
    pin = hash_pin(pin, account_uuid)
    if pin:
        logger.verbose(f"Updating Pin for account {account_uuid}...")
        with db_helper.cursor() as cur:
            cur.execute("SELECT * FROM bank_accounts WHERE uuid = %s", (account_uuid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Account not found"}), 404
            account = cast(Dict[str, Any], row)
            if int(account["account_holder_id"]) != int(user_id):
                return jsonify({"error": "Account not found"}), 404
            if str(account["account_holder_type"]) != "user":
                logger.verbose("Invalid Account Type. Non Personal Account attempting Pin Change")
                return jsonify({"error": "Account not found"}), 404
            cur.execute("UPDATE bank_accounts SET pin_hash = %s WHERE uuid = %s", (pin, account_uuid))
        return jsonify({"success": True, "message": "Account updated"})
    else:
        return jsonify({"error": "Invalid JSON"}), 400


# Public Acc lookup
@bp.route("/public/<uuid:account_uuid>", methods=["GET"])
def lookup_uuid(account_uuid):
    account_uuid = str(account_uuid)
    logger.verbose(f"Retrieving public info from {account_uuid}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT balance, id, is_frozen, account_number, account_holder_id, account_holder_type FROM bank_accounts WHERE uuid = %s", (account_uuid,))
        row = cur.fetchone()
        account = cast(Dict[str, Any], row)
        if not row or account["is_frozen"]:
            return jsonify({"error": "Account not found"}), 404
        account_number = account["account_number"]
        balance = account["balance"]
        holder = account["account_holder_id"]
        acc_id = account["id"]
        acctype = str(account["account_holder_type"])
        if acctype == "user":
            cur.execute("SELECT username FROM users WHERE id = %s",(holder,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Account not found"}), 404 
            user = cast(Dict[str, Any], row)
            holder = str(user["username"])
        elif acctype == "company":
            # to be implemented
            holder = "Unknown Company"
        else:
            holder = "Unknown Company"
    return jsonify({
        "account_number": account_number,
        "balance": balance,
        "holder": holder,
        "id": acc_id,
    }), 200

@bp.route("/public/<string:accnum>", methods=["GET"])
def lookup_accnum(accnum):
    with db_helper.cursor() as cur:
        cur.execute("SELECT balance, id, is_frozen, uuid, account_holder_id, account_holder_type FROM bank_accounts WHERE account_number  = %s", (accnum,))
        row = cur.fetchone()
        account = cast(Dict[str, Any], row)
        if not row or account["is_frozen"]:
            return jsonify({"error": "Account not found"}), 404
        logger.verbose(f"Retrieving public info from {account['uuid']}...")
        account_uuid = account["uuid"]
        balance = account["balance"]
        acc_id = account["id"]
        holder = account["account_holder_id"]
        acctype = str(account["account_holder_type"])
        if acctype == "user":
            cur.execute("SELECT username FROM users WHERE id = %s",(holder,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Account not found"}), 404 
            user = cast(Dict[str, Any], row)
            holder = str(user["username"])
        elif acctype == "company":
            # to be implemented
            holder = "Unknown Company"
        else:
            holder = "Unknown Company"
    return jsonify({
        "account_uuid": account_uuid,
        "balance": balance,
        "holder": holder,
        "id": acc_id,
    }), 200

