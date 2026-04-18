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
    logger.verbose(f"Getting transaction data for {data['id']}")
    with db_helper.cursor() as cur:
        cur.execute("SELECT uuid, transaction_type, from_account_id, to_account_id, amount, confirmed, created_at, description, metadata, tax_category FROM transactions WHERE uuid = %s", (tx_uuid,))
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
        amount = Decimal(str(req["amount"])).quantize(Decimal("0.001"))
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
        amount = Decimal(str(req["amount"])).quantize(Decimal("0.001"))
    except Exception:
        return jsonify({"error": "Invalid amount"}), 400
    if amount <= 0:
        return jsonify({"error": "Amount must be positive"}), 400 #try requesting money instead

    match tax_category:
        case "1":
            tax = Decimal("0.300") # 30% Tax, hardcoded until Government System
            tax_amount = (amount * tax).quantize(Decimal("0.001"))
            final_amount = amount + tax_amount
        case _:
            tax_amount = Decimal("0.000")
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

            if tax_amount > 0:
                tax = Decimal("0.300") # 30% Tax, hardcoded until Government System
                description = str(f"30% Tax - ID: {transaction_id}")
                gov_tax_account: int = 26
                metadata = json.dumps({"tax": str(tax), "tax_amount": str(tax_amount), "tax_category": tax_category, "transaction_id": transaction_id})
                cur.execute("""
                    INSERT INTO transactions (
                        transaction_type, 
                        from_account_id,
                        to_account_id,
                        amount,
                        tax_category,
                        description,
                        metadata,
                        confirmed
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, ("tax", donor["id"], gov_tax_account, tax_amount, tax_category, description, metadata, 1))
                tax_id = cur.lastrowid
                cur.execute(
                    "UPDATE bank_accounts SET balance = balance - %s WHERE id = %s",
                    (tax_amount, donor["id"])
                )
                cur.execute(
                    "UPDATE bank_accounts SET balance = balance + %s WHERE id = %s",
                    (tax_amount, gov_tax_account)
                )
            else:
                tax_id = ""
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

     