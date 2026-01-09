from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from typing import Dict, Any, cast
import os
from decimal import Decimal

bp = Blueprint("transactions", __name__, url_prefix="/api/bank")


@bp.route("/transactions", methods=["GET"])
@require_token
def get_all_transactions(data):
    logger.verbose(f"Getting transaction data for {data['id']}")
    with db_helper.cursor() as cur:
        cur.execute("SELECT uuid, transaction_type, from_account_id, to_account_id, amount, confirmed, created_at, description, metadata, tax_category FROM transactions WHERE to_account_id = %s OR from_account_id = %s", (data["id"]), (data["id"]))
        rows = cur.fetchall()
        return jsonify({"transactions": rows}), 200


@bp.route("/transactions/<uuid:tx_uuid>", methods=["GET"])
@require_token
def get_transaction(data, tx_uuid):
    logger.verbose(f"Getting transaction data for {data['id']}")
    with db_helper.cursor() as cur:
        cur.execute("SELECT uuid, transaction_type, from_account_id, to_account_id, amount, confirmed, created_at, description, metadata, tax_category FROM transactions WHERE uuid = %s", (tx_uuid))
        row = cur.fetchone()
        return jsonify({"transaction": row}), 200

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

            donor = cast(Dict[str, Any], donor_row)
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

            receiver = cast(Dict[str, Any], receiver_row)
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
    tax_category = req["tax_category"]

    # Validate and parse amount as Decimal
    try:
        amount = Decimal(str(req["amount"]))
    except Exception:
        return jsonify({"error": "Invalid amount"}), 400
    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400 #try requesting money instead

    match tax_category:
        case "1":
            tax = Decimal(0.300) # 30% Tax, hardcoded until Government System
            final_amount = amount * (1 + tax)
        case _:
            final_amount = amount
        
    # Use transaction for atomicity
    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
            # --- Validate donor account: must exist and be owned by user ---
            cur.execute("""
                SELECT id, balance 
                FROM bank_accounts 
                WHERE uuid = %s 
                  AND account_holder_type = 'user' 
                  AND account_holder_id = %s 
                  AND is_deleted = 0
            """, (donor_uuid, str(user_id)))
            donor_row = cur.fetchone()
            if donor_row is None:
                return jsonify({"error": "Donor account not found or not owned"}), 404

            donor = cast(Dict[str, Any], donor_row)
            if donor["balance"] < final_amount:
                return jsonify({"error": "Insufficient funds"}), 402

            # --- Validate receiver account: must exist, be owned by SAME user ---
            cur.execute("""
                SELECT id, is_frozen
                FROM bank_accounts 
                WHERE uuid = %s
                  AND is_deleted = 0
            """, (receiver_uuid, str(user_id)))
            receiver_row = cur.fetchone()
            if receiver_row is None:
                return jsonify({"error": "Receiver account not found"}), 404

            receiver = cast(Dict[str, Any], receiver_row)

            
            if donor["is_frozen"] | receiver["is_frozen"]:
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
                ) VALUES (%s, %s, %s, %s, %s)
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
                    tax = Decimal(0.300) # 30% Tax, hardcoded until Government System
                    tax_amount = amount - (amount * (1 + tax))
                    cur.execute("""
                        INSERT INTO transactions (
                            transaction_type, 
                            from_account_id, 
                            to_account_id, 
                            amount,
                            tax_category,
                            confirmed
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, ("tax", donor["id"], "1", tax_amount, tax_category, 1))
                    tax_id = cur.lastrowid
                    cur.execute(
                        "UPDATE bank_accounts SET balance = balance - %s WHERE id = %s",
                        (tax_amount, donor["id"])
                    )
                    cur.execute(
                        "UPDATE bank_accounts SET balance = balance + %s WHERE id = %s",
                        (tax_amount, "1")
                    )
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

     