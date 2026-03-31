from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from typing import Any, cast
import os
from decimal import Decimal
import simplejson as json

bp = Blueprint("bank", __name__, url_prefix="/api/bank")


@bp.route("/view-transactions", methods=["POST"])
@require_token
def get_all_transactions(data):
    user_id = data["id"]  # internal int ID from JWT
    req = request.get_json()

    if not req or not all(k in req for k in ("acc_id",)):
        return jsonify({"error": "Missing required fields"}), 400

    account_id = req["acc_id"]
    logger.verbose(f"Getting transaction data for {account_id}")
    with db_helper.cursor() as cur:
        cur.execute("SELECT account_holder_id FROM bank_accounts WHERE id = %s", (account_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        parse = cast(dict[str, Any], row)
        if int(parse["account_holder_id"]) != int(user_id):
            return jsonify({"error": "Account not found"}), 404
        cur.execute("SELECT uuid, transaction_type, from_account_id, to_account_id, amount, confirmed, created_at, description, metadata, tax_category FROM transactions WHERE to_account_id = %s OR from_account_id = %s", (account_id, account_id,))
        rows = cur.fetchall()
        return jsonify({"transactions": rows}), 200


@bp.route("/view-transactions/<uuid:tx_uuid>", methods=["GET"])
@require_token
def get_transaction(data, tx_uuid):
    user_id, user_role = data.get("id"), data.get("role", "user")
    logger.verbose(f"Getting transaction data for user {user_id}, tx {tx_uuid}")

    with db_helper.cursor() as cur:
        # Avoid SELECT * to prevent over-exposure of internal fields.
        query = """
            SELECT
                t.uuid, t.transaction_type, t.from_account_id, t.to_account_id,
                t.amount, t.confirmed, t.created_at, t.description, t.metadata, t.tax_category,
                fa.account_holder_id AS from_holder, ta.account_holder_id AS to_holder
            FROM transactions t
            LEFT JOIN bank_accounts fa ON t.from_account_id = fa.id
            LEFT JOIN bank_accounts ta ON t.to_account_id = ta.id
            WHERE t.uuid = %s
        """
        cur.execute(query, (str(tx_uuid),))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Transaction not found"}), 404

        tx = cast(dict[str, Any], row)
        # Auth check: Participant or Admin/Mod. Return 404 on failure to prevent ID enumeration.
        is_owner = str(tx.get("from_holder")) == str(user_id) or str(tx.get("to_holder")) == str(user_id)
        if not is_owner and user_role not in ["admin", "mod"]:
            logger.warning(f"Unauthorized access to tx {tx_uuid} by user {user_id}")
            return jsonify({"error": "Transaction not found"}), 404

        # Return explicit list of fields to maintain the original API contract
        res = {k: tx[k] for k in ["uuid", "transaction_type", "from_account_id", "to_account_id", "amount", "confirmed", "created_at", "description", "metadata", "tax_category"]}
        if res.get("created_at") and hasattr(res["created_at"], "isoformat"):
            res["created_at"] = res["created_at"].isoformat()
        return jsonify({"transaction": res}), 200

@bp.route("/transactions", methods=["POST"])
@require_token
def transfer(data):
    """
        Transfer funds between two bank accounts owned by the authenticated user.
        Both accounts must belong to the same user.
    """
    logger.verbose("Transfer initialized...")

    user_id = data["id"]  # internal int ID from JWT
    req = request.get_json()

    if not req or not all(k in req for k in ("from_account", "to_account", "amount")):
        return jsonify({"error": "Missing required fields"}), 400

    donor_uuid = req["from_account"]
    receiver_uuid = req["to_account"]

    # Validate and parse amount as Decimal
    try:
        amount = Decimal(str(req["amount"]))
    except Exception:
        return jsonify({"error": "Invalid amount"}), 400
    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400


    # Use transaction for atomicity
    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
            # --- Validate donor account: must exist and be owned by user ---
            cur.execute("""
                SELECT id, balance, is_frozen
                FROM bank_accounts 
                WHERE uuid = %s 
                  AND account_holder_type = 'user' 
                  AND account_holder_id = %s 
                  AND is_deleted = 0
            """, (donor_uuid, str(user_id)))
            donor_row = cur.fetchone()
            if donor_row is None:
                return jsonify({"error": "Donor account not found or not owned"}), 404

            donor = cast(dict[str, Any], donor_row)
            if donor["balance"] < amount:
                return jsonify({"error": "Insufficient funds"}), 402

            # --- Validate receiver account: must exist, be owned by SAME user ---
            cur.execute("""
                SELECT id, is_frozen
                FROM bank_accounts 
                WHERE uuid = %s 
                  AND account_holder_type = 'user' 
                  AND account_holder_id = %s 
                  AND is_deleted = 0
            """, (receiver_uuid, str(user_id)))
            receiver_row = cur.fetchone()
            if receiver_row is None:
                return jsonify({"error": "Receiver account not found or not owned"}), 404

            receiver = cast(dict[str, Any], receiver_row)
            if receiver["is_frozen"] | donor["is_frozen"]:
                return jsonify({"error": "Account is frozen"}), 403
            # --- Record transaction (confirmed = 1 immediately) ---
            cur.execute("""
                INSERT INTO transactions (
                    transaction_type, 
                    from_account_id, 
                    to_account_id, 
                    amount,
                    confirmed
                ) VALUES (%s, %s, %s, %s, %s)
            """, ("transfer", donor["id"], receiver["id"], amount, 1))
            transaction_id = cur.lastrowid

            # --- Atomically update balances ---
            cur.execute(
                "UPDATE bank_accounts SET balance = balance - %s WHERE id = %s",
                (amount, donor["id"])
            )
            cur.execute(
                "UPDATE bank_accounts SET balance = balance + %s WHERE id = %s",
                (amount, receiver["id"])
            )

            logger.verbose(f"Transfer of {amount} completed. TX ID: {transaction_id}")

        finally:
            cur.close()

    return jsonify({
        "success": True,
        "message": "Transfer successful",
        "transaction_id": transaction_id
    }), 200

@bp.route("/pay", methods=["POST"])
@require_token
def make_payment(data):
    """
        Makes a payment to a bank account with their UUID using a bank account from a authenticated user.
    """
    logger.verbose("Payment initialized...")

    user_id = data["id"]  # internal int ID from JWT
    req = request.get_json()

    if not req or not all(k in req for k in ("from_account", "to_account", "amount", "description", "tax_category")):
        return jsonify({"error": "Missing required fields"}), 400

    donor_uuid = req["from_account"]
    receiver_uuid = req["to_account"]
    description = req["description"]
    tax_category = str(req["tax_category"])

    # Validate and parse amount as Decimal
    try:
        amount = Decimal(str(req["amount"]))
    except Exception:
        return jsonify({"error": "Invalid amount"}), 400
    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400 #try requesting money instead

    match tax_category:
        case "1":
            tax = Decimal("0.300") # 30% Tax, hardcoded until Government System
            final_amount = amount * (1 + tax)
        case _:
            final_amount = amount
        
    # Use transaction for atomicity
    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
            # --- Validate donor account: must exist and be owned by user ---
            cur.execute("""
                SELECT id, balance, is_frozen
                FROM bank_accounts 
                WHERE uuid = %s 
                  AND account_holder_type = 'user' 
                  AND account_holder_id = %s 
                  AND is_deleted = 0
            """, (donor_uuid, str(user_id)))
            donor_row = cur.fetchone()
            if donor_row is None:
                return jsonify({"error": "Donor account not found or not owned"}), 404

            donor = cast(dict[str, Any], donor_row)
            if donor["balance"] < final_amount:
                return jsonify({"error": "Insufficient funds"}), 402

            # --- Validate receiver account: must exist, be owned by SAME user ---
            cur.execute("""
                SELECT id, is_frozen
                FROM bank_accounts 
                WHERE uuid = %s
                  AND is_deleted = 0
            """, (receiver_uuid,))
            receiver_row = cur.fetchone()
            if receiver_row is None:
                return jsonify({"error": "Receiver account not found"}), 404

            receiver = cast(dict[str, Any], receiver_row)

            
            if donor["is_frozen"] or receiver["is_frozen"]:
                return jsonify({"error": "Account is frozen"}), 403
            # --- Record transaction (confirmed = 1 immediately) ---
            cur.execute("""
                INSERT INTO transactions (
                    transaction_type, 
                    from_account_id, 
                    to_account_id, 
                    amount,
                    tax_category,
                    description,
                    confirmed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, ("payment", donor["id"], receiver["id"], amount, tax_category, description, 1))
            transaction_id = cur.lastrowid

            # --- Atomically update balances ---
            cur.execute(
                "UPDATE bank_accounts SET balance = balance - %s WHERE id = %s",
                (amount, donor["id"])
            )
            cur.execute(
                "UPDATE bank_accounts SET balance = balance + %s WHERE id = %s",
                (amount, receiver["id"])
            )

            match tax_category:
                case "1":
                    tax = Decimal("0.300") # 30% Tax, hardcoded until Government System
                    tax_amount = (amount * (1 + tax)) - amount

                    description = str(f"30% Tax - ID: {transaction_id}")
                    metadata = json.dumps({"tax": tax, "tax_amount": tax_amount, "tax_category": tax_category, "transaction_id": transaction_id})
                    cur.execute("""
                        INSERT INTO transactions (
                            transaction_type, 
                            from_account_id,
                            amount,
                            tax_category,
                            description,
                            metadata,
                            confirmed
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, ("tax", donor["id"], tax_amount, tax_category, description, metadata, 1))
                    tax_id = cur.lastrowid
                    cur.execute(
                        "UPDATE bank_accounts SET balance = balance - %s WHERE id = %s",
                        (tax_amount, donor["id"])
                    )
                    # cur.execute(
                    #    "UPDATE bank_accounts SET balance = balance + %s WHERE id = %s",
                    #    (tax_amount, "1")
                    #)
                case _:
                    tax_id = ""
                    pass
            logger.verbose(f"Payment of {amount} completed. TX ID: {transaction_id}, Tax ID: {tax_id}")

        finally:
            cur.close()
    # here would come a notification call to the reciever later
    return jsonify({
        "success": True,
        "message": "Payment successful",
        "transaction_id": transaction_id,
        "tax_id": tax_id
    }), 200

     