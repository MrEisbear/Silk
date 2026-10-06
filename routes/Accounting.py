from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token, hash_pin
from core.database import db_helper
from core.logger import logger
from typing import  Any, cast
from core.coreRandUtil import generate_account_number


bp = Blueprint("accounting", __name__, url_prefix="/api/bank")


@bp.route("/accounts", methods=["GET"])
@require_token
def get_user_accounts(data):
    user_id = data["id"]
    logger.verbose(f"Retrieving bank accounts of {user_id}...")
    with db_helper.cursor() as cur:
        cur.execute(
            """
            SELECT 
                id,
                uuid,
                account_number,
                account_holder_type,
                account_holder_id,
                balance,
                custom_account_name,
                custom_account_name AS account_name,
                notes,
                is_frozen,
                (pin_hash IS NOT NULL) AS has_pin,
                created_at,
                updated_at
            FROM bank_accounts 
            WHERE account_holder_id = %s 
              AND account_holder_type = 'user' 
              AND is_deleted = 0
            """,
            (user_id,)
        )
        rows = cur.fetchall()
        for row in rows:
            if row.get("created_at") and hasattr(row["created_at"], "isoformat"):
                row["created_at"] = row["created_at"].isoformat()
            if row.get("updated_at") and hasattr(row["updated_at"], "isoformat"):
                row["updated_at"] = row["updated_at"].isoformat()
            if "is_frozen" in row:
                row["is_frozen"] = bool(row["is_frozen"])
            if "has_pin" in row:
                row["has_pin"] = bool(row["has_pin"])
        return jsonify({"accounts": rows})

@bp.route("/accounts", methods=["POST"])
@require_token
def create_user_accounts(data):
    user_id = data["id"]
    logger.verbose(f"Creating bank accounts for {user_id}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        user = cast(dict[str, Any], row)
        discord_id = user["discord_id"]
        if discord_id is None:
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
        first_account = False
        try:
            cur.execute("SELECT COUNT(*) as count FROM bank_accounts WHERE account_holder_id = %s AND account_holder_type = 'user' AND is_deleted = 0", (user_id,))
            result = cur.fetchone()
            count = int(cast(dict[str, int], result)["count"]) if result else 0
            if count >= 5:
                return {"error": "Maximum account limit reached, contact support to create additional accounts."}, 400
            if count == 0:
                first_account = True
            
            cur.execute("INSERT INTO bank_accounts (account_number, account_holder_type, account_holder_id) VALUES (%s, %s, %s)", (accnum, 'user', user_id,))
        except Exception as e:
            logger.error(str(e))
            return jsonify({"error": "Failed to create bank account"}), 500
        
        if first_account:
            start_money = 7500
            cur.execute(
                "UPDATE bank_accounts SET balance = balance + %s WHERE account_number = %s", 
                (start_money, accnum)
            )
    logger.verbose(f"Bank Account created for {user_id}; {accnum}")
    
    return jsonify({"account_number": accnum}), 201

@bp.route("/accounts/<uuid:account_uuid>", methods=["GET"])
@require_token
def retrieve_acc_details(data, account_uuid):
    user_id = data["id"]
    account_uuid = str(account_uuid)
    logger.verbose(f"Retrieving bank account {account_uuid}...")
    with db_helper.cursor() as cur:
        cur.execute(
            """
            SELECT 
                id,
                uuid,
                account_number,
                account_holder_type,
                account_holder_id,
                balance,
                custom_account_name,
                custom_account_name AS account_name,
                notes,
                is_frozen,
                (pin_hash IS NOT NULL) AS has_pin,
                created_at,
                updated_at
            FROM bank_accounts 
            WHERE uuid = %s AND is_deleted = 0
            """,
            (account_uuid,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        account = cast(dict[str, Any], row)
        if int(account["account_holder_id"]) != int(user_id):
            return jsonify({"error": "Account not found"}), 404
        return jsonify({
            "id": account["id"],
            "uuid": account["uuid"],
            "account_number": account["account_number"],
            "account_name": account["custom_account_name"],
            "custom_account_name": account["custom_account_name"],
            "notes": account["notes"],
            "balance": account["balance"],
            "is_frozen": bool(account["is_frozen"]),
            "has_pin": bool(account["has_pin"]),
            "account_holder_type": account["account_holder_type"],
            "account_holder_id": account["account_holder_id"],
            "created_at": account["created_at"].isoformat() if account["created_at"] and hasattr(account["created_at"], "isoformat") else account["created_at"],
            "updated_at": account["updated_at"].isoformat() if account["updated_at"] and hasattr(account["updated_at"], "isoformat") else account["updated_at"],
        })

@bp.route("/accounts/<uuid:account_uuid>", methods=["PATCH"])
@require_token
def update_acc_details(data, account_uuid):
    user_id = data["id"]
    account_uuid = str(account_uuid)
    req = request.get_json()
    if not req:
        return jsonify({"error": "Invalid JSON"}), 400

    # --- Validate all fields up-front before touching the DB ---
    updates: dict[str, Any] = {}

    if "is_frozen" in req:
        freeze = req["is_frozen"]
        if not isinstance(freeze, bool):
            return jsonify({"error": "is_frozen must be a boolean"}), 400
        updates["is_frozen"] = freeze

    if "pin" in req:
        pin = str(req["pin"])
        if len(pin) not in [4, 5, 6]:
            return jsonify({"error": "Pin must be 4-6 digits"}), 400
        updates["pin"] = pin          # hashed after ownership check

    if "account_name" in req or "custom_account_name" in req:
        account_name = req.get("account_name") if "account_name" in req else req.get("custom_account_name")
        if account_name is False or account_name is None or account_name == "" or (isinstance(account_name, str) and account_name.strip().lower() == "false"):
            updates["custom_account_name"] = None
        elif isinstance(account_name, str):
            if len(account_name) > 36:
                return jsonify({"error": "account_name must be at most 36 characters"}), 400
            updates["custom_account_name"] = account_name
        else:
            return jsonify({"error": "account_name must be a string, null, or false"}), 400

    if "notes" in req:
        notes = req["notes"]
        if notes is False or notes is None or notes == "" or (isinstance(notes, str) and notes.strip().lower() == "false"):
            updates["notes"] = None
        elif isinstance(notes, str):
            updates["notes"] = notes
        else:
            return jsonify({"error": "notes must be a string, null, or false"}), 400

    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    # --- Single DB round-trip for lookup + ownership ---
    logger.verbose(f"Updating bank account {account_uuid}...")
    with db_helper.cursor() as cur:
        cur.execute(
            "SELECT id, account_holder_id, account_holder_type FROM bank_accounts WHERE uuid = %s AND is_deleted = 0",
            (account_uuid,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        account = cast(dict[str, Any], row)
        if int(account["account_holder_id"]) != int(user_id):
            return jsonify({"error": "Account not found"}), 404

        # Pin change is only allowed for personal accounts
        if "pin" in updates:
            if str(account["account_holder_type"]) != "user":
                logger.verbose("Invalid Account Type. Non Personal Account attempting Pin Change")
                return jsonify({"error": "Account not found"}), 404
            hashed = hash_pin(updates.pop("pin"), account_uuid)
            if hashed:
                updates["pin_hash"] = hashed

        # Build a single UPDATE statement
        set_clauses = ", ".join(f"{col} = %s" for col in updates)
        values = list(updates.values()) + [account_uuid]
        cur.execute(f"UPDATE bank_accounts SET {set_clauses} WHERE uuid = %s", values)

    return jsonify({"success": True, "message": "Account updated"})

# Public Acc lookup
@bp.route("/public/<uuid:account_uuid>", methods=["GET"])
def lookup_uuid(account_uuid):
    account_uuid = str(account_uuid)
    logger.verbose(f"Retrieving public info from {account_uuid}...")
    with db_helper.cursor() as cur:
        cur.execute("SELECT balance, id, is_frozen, account_number, account_holder_id, account_holder_type FROM bank_accounts WHERE uuid = %s", (account_uuid,))
        row = cur.fetchone()
        account = cast(dict[str, Any], row)
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
            user = cast(dict[str, Any], row)
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

@bp.route("/public/<int:acc_id>", methods=["GET"])
def lookup_id(acc_id: int):
    with db_helper.cursor() as cur:
        cur.execute("""
            SELECT 
                b.account_number,
                CASE
                    WHEN b.account_holder_type = 'user' THEN u.username
                    WHEN b.account_holder_type = 'gov' THEN 'Gov Entity'
                    WHEN b.account_holder_type = 'company' THEN 'Company'
                    ELSE 'Unknown'
                END AS holder
            FROM bank_accounts b
            LEFT JOIN users u
                ON b.account_holder_type = 'user'
                AND u.id = CAST(b.account_holder_id AS UNSIGNED)
            WHERE b.id = %s
              AND b.is_deleted = 0
            LIMIT 1
        """, (acc_id,))

        row = cur.fetchone()
        if not row:
            return {"error": "Account not found"}, 404
    result = cast(dict[str, Any], row)
    return result, 200
        
@bp.route("/public/<string:accnum>", methods=["GET"])
def lookup_accnum(accnum: str):
    with db_helper.cursor() as cur:
        cur.execute("SELECT balance, id, is_frozen, uuid, account_holder_id, account_holder_type FROM bank_accounts WHERE account_number  = %s", (accnum,))
        row = cur.fetchone()
        account = cast(dict[str, Any], row)
        if not row or account["is_frozen"]:
            return jsonify({"error": "Account not found"}), 404
        logger.verbose(f"Retrieving public info from {account['uuid']}...")
        account_uuid = account["uuid"]
        balance = account["balance"]
        acc_id = account["id"]
        holder = account["account_holder_id"]
        acctype = str(account["account_holder_type"])
        match acctype:
            case "user":
                cur.execute("SELECT username FROM users WHERE id = %s",(holder,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "Account not found"}), 404 
                user = cast(dict[str, Any], row)
                holder = str(user["username"])
            case "company":
                # to be implemented
                holder = "Unknown Company"
            case "gov":
                holder = "Regierung"
                match accnum:
                    case "G-10091a4":
                        holder = "Allgemeine Staatskasse"
                    case "G-4003854":
                        holder = "Andere"
                    case "G-3006707":
                        holder = "Strafgelder"
                    case "G-200a869":
                        holder = "Steuern"
                    case _:
                        pass
            case _:
                holder = "Unknown Company"
    return jsonify({
        "account_uuid": account_uuid,
        "balance": balance,
        "holder": holder,
        "id": acc_id,
    }), 200

