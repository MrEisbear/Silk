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
                    metadata
                ) VALUES (%s, %s, %s, %s, %s)
            """, ("giftcard", acc_id, amount, 1, json.dumps(metadata)))
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