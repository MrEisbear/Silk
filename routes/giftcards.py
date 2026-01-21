from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from typing import Dict, Any, cast
import os
from decimal import Decimal
import secrets
import string
from whenever import Instant, minutes, hours
import json

bp = Blueprint("giftcards", __name__, url_prefix="/api/bank")

def gen_giftcode(length=16):
    # Generates a string of random digits
    return ''.join(secrets.choice(string.digits) for _ in range(length))

@bp.route("/giftcards/redeem", methods=["POST"])
@require_token
def redeem_giftcard(data):
    user_id = data["id"]
    req = request.get_json()
    
    if not req or not all(k in req for k in ("code", "to_account",)):
        return jsonify({"error": "Missing required fields"}), 400
    
    code = req["code"]
    to_account = req["to_account"]
    
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM gift_codes WHERE code = %s", (code,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Giftcard not found"}), 404
        giftcard = cast(Dict[str, Any], row)
        amount = giftcard["amount"]
        source_acc = giftcard["created_by"]
        expires_at = giftcard["expires_at"] 
        
        if Instant.now().py_datetime() > expires_at:
            metadata = {
                "code": code,
                "provider": "LinePay"
            }
            
            cur.execute("""
            INSERT INTO transactions (
                transaction_type, 
                to_account_id,
                amount,
                confirmed,
                description,
                metadata
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """, ("refund", source_acc, amount, 1, str(f"Giftcard expired {code[-4:]}"), json.dumps(metadata)))
            transaction_id = cur.lastrowid
            
            cur.execute("UPDATE gift_codes SET is_active = %s WHERE code = %s", (0, code,))
            cur.execute("UPDATE bank_accounts SET balance = balance + %s WHERE id = %s",
                (amount, source_acc,))
            if cur.rowcount == 0:
                logger.fatal(f"Refund failed, Amount: {amount}, Code: {code}")
            return jsonify({"error": "Giftcard expired"}), 403
        
        # Give Money back to original account?
        
        cur.execute("SELECT * FROM bank_accounts WHERE uuid = %s", (to_account,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        account = cast(Dict[str, Any], row)
        balance = account["balance"]

        holder = account["account_holder_id"]
        acc_id = account["id"]
        validify2 = int(account["is_frozen"])
        validify1 = str(account["account_holder_type"])
        if validify1 != "user":
            return jsonify({"error": "Account not found"}), 404
        if validify2 != 0:
            return jsonify({"error": "Account not found"}), 404
        if int(holder) != int(user_id):
            return jsonify({"error": "Account not found"}), 404

        redeemed_at = Instant.now().py_datetime()
        desc = f"Redeemed Giftcard (****-{code[-4:]})"
        
        metadata = {
        "code": code,
        "balance": Decimal(0.000),
        "provider": "LinePay"
        }
            
        with db_helper.transaction() as db:
            cur = db.cursor(dictionary=True)
            try:
                cur.execute("""
                INSERT INTO transactions (
                    transaction_type, 
                    to_account_id,
                    amount,
                    confirmed,
                    description,
                    metadata
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """, ("giftcard", acc_id, amount, 1, str(desc), json.dumps(metadata)))
                transaction_id = cur.lastrowid
            
                cur.execute("""
                        UPDATE gift_codes SET
                        redeemed_by = %s,
                        redeemed_at = %s,
                        is_active = %s
                        """, (acc_id, redeemed_at, 0))
                cur.execute("UPDATE bank_accounts SET balance = balance + %s WHERE uuid = %s",
                    (amount, to_account))
            finally:
                cur.close()
            return jsonify({
                "transaction_id": transaction_id,
                "amount": amount
            }), 200
                
        

@bp.route("/giftcards/create", methods=["POST"])
@require_token
def create_giftcard(data):
    user_id = data["id"]  # internal int ID from JWT
    req = request.get_json()

    if not req or not all(k in req for k in ("source_account", "amount",)):
        return jsonify({"error": "Missing required fields"}), 400

    source_acc = req["source_account"]
    amount = req["amount"]
    
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM bank_accounts WHERE uuid = %s", (source_acc,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        account = cast(Dict[str, Any], row)
        money = account["balance"]
        holder = account["account_holder_id"]
        acc_id = account["id"]
        validify2 = int(account["is_frozen"])
        validify1 = str(account["account_holder_type"])
        if validify1 != "user":
            return jsonify({"error": "Account not found"}), 404
        if validify2 != 0:
            return jsonify({"error": "Account not found"}), 404
        if int(holder) != int(user_id):
            return jsonify({"error": "Account not found"}), 404
        if money < amount:
            return jsonify({"error": "Insufficient funds"}), 402

    code = gen_giftcode()
    expires_at = Instant.now() + hours(365 * 24)
    expires_at = expires_at.py_datetime()
    
    metadata = {
        "code": code,
        "expires": expires_at.isoformat(),
        "provider": "LinePay"
    }
    
    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
            cur.execute("""
                INSERT INTO transactions (
                    transaction_type, 
                    from_account_id,
                    amount,
                    confirmed,
                    description,
                    metadata
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, ("giftcard", acc_id, amount, 1, str(f"Code: {code}"), json.dumps(metadata)))
            transaction_id = cur.lastrowid
            
            cur.execute("""
                    INSERT INTO gift_codes (
                        code,
                        amount,
                        created_by,
                        expires_at
                    ) VALUES (%s, %s, %s, %s)
                """, (code, amount, acc_id, expires_at))
            cur.execute(
                "UPDATE bank_accounts SET balance = balance - %s WHERE uuid = %s",
                (amount, source_acc)
            )               
        finally:
            cur.close() 
    return jsonify({
        "transaction_id": transaction_id,
        "code": code
    }), 201