from posix import TMP_MAX
from flask import Blueprint, redirect, request, jsonify
from core.coreAuthUtil import hash_password, check_password, create_jwt, require_token, hash_pin, check_pin
from core.database import db_helper
from whenever import Instant, minutes
from core.logger import logger
from typing import cast, Any, Callable
import os
import requests
from urllib.parse import urlencode
from decimal import Decimal, InvalidOperation
import secrets
from ua_parser import user_agent_parser
import simplejson as json
from base64 import b64decode

bp = Blueprint("pay", __name__, url_prefix="/api/pay")

@bp.route("/token", methods=["POST"])
def issue_SP_token():
    """
    Issues single pay token.
    """
    logger.verbose("SP Token requested...")
    req = request.get_json()
    # First check if all arguments are given
    if not req or not all(k in req for k in ("amount", "tax", "pin", "recipient_type", "recipient_uuid", "sender_type", "sender_accnum")):
        return jsonify({"error": "Missing required fields"}), 400
    
    # Verify Amount Decimal(19,3)
    amount = req["amount"]
    try:
        amount = Decimal(str(amount))
        if amount <= 0:
            return jsonify({"error": "Amount must be positive"}), 400
        if amount.quantize(Decimal("0.001")) != amount:
            return jsonify({"error": "Amount cannot have more than 3 decimal places"}), 400
        if amount >= Decimal("10000000000000000"):
            return jsonify({"error": "Amount too large"}), 400
    except (ValueError, InvalidOperation):
        return jsonify({"error": "Invalid amount"}), 400
    
    
    sender_accnum = req["sender_accnum"]
    pin = req["pin"]
    reciever_type = req["recipient_type"]
    sender_type = req["sender_type"]
    if int(sender_type) != 1:
        return jsonify({"error": "PIN Auth, unavailable for non-personal accounts."}), 400
    
    with db_helper.cursor() as cur:
        cur.execute("SELECT * FROM bank_accounts WHERE account_number = %s", (sender_accnum,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        sender = cast(dict[str, Any], row)
        if sender["pin_locked_until"] is not None:
            locked_until = Instant.from_timestamp(sender["pin_locked_until"].timestamp())
            if Instant.now() < locked_until:
                return jsonify({"error": "Account is locked"}), 403
        if not sender["pin_hash"]:
            return jsonify({"error": "PIN not set"}), 400
        if not check_pin(pin, sender["uuid"], sender["pin_hash"]):
            attempts = sender["pin_failed_attempts"] + 1
            if attempts >= 3:
                cur.execute("UPDATE bank_accounts SET pin_locked_until = DATE_ADD(NOW(), INTERVAL 15 MINUTE) WHERE uuid = %s", (sender["uuid"],))
            else: 
                cur.execute("UPDATE bank_accounts SET pin_failed_attempts = %s WHERE uuid = %s", (attempts, sender["uuid"],))
            return jsonify({"error": "Invalid PIN"}), 401
        cur.execute("UPDATE bank_accounts SET pin_failed_attempts = 0, pin_locked_until = NULL WHERE uuid = %s",
        (sender["uuid"],))
        if sender["balance"] < amount:
            return jsonify({"error": "Insufficient funds"}), 402
        sender_uuid = sender["uuid"]
        cur.execute("SELECT * FROM bank_accounts WHERE uuid = %s", (req["recipient_uuid"],))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Account not found"}), 404
        reciever = cast(dict[str, Any], row)
        if int(sender["is_frozen"]) != 0 or int(reciever["is_frozen"]) != 0:
            return jsonify({"error": "Account is frozen"}), 403
        if int(sender["is_deleted"]) != 0 or int(reciever["is_deleted"]) != 0:
            return jsonify({"error": "Account not found"}), 403
        
        # Only Users as recievers available for now
        if int(reciever_type) != 1:
            return jsonify({"error": "Not Implemented"}), 501

        token = secrets.token_hex(32)
        expires_at = Instant.now() + minutes(10)
        expires_at = expires_at.py_datetime()
        label = req.get("label")
        webhook_b64 = req.get("webhook")
        if req.get("plain_webhook"):
            webhook = req.get("plain_webhook")
        elif webhook_b64:
            try:
                webhook = b64decode(webhook_b64).decode("utf-8")
            except Exception as e:
                logger.fatal(str(e))
                return jsonify({"error": "Internal Server Error"}), 500
        else:
            webhook = None
        
        if webhook:
            allowed_list = ("discord.com/api/webhooks/",)
            if not webhook.startswith("https://"):
                return jsonify({"error": "Invalid webhook URL"}), 400
            if len(webhook) > 2000:
                return jsonify({"error": "Webhook too long"}), 400    
            if not any(d in webhook for d in allowed_list):
                return jsonify({"error": "Webhook domain not allowed"}), 400
        
        raw_ua = request.headers.get("User-Agent", "")
        parsed_ua = user_agent_parser.Parse(raw_ua)
        ua_data = json.dumps({
            "browser": parsed_ua['user_agent']['family'],
            "version": parsed_ua['user_agent']['major'],
            "os": parsed_ua['os']['family'],
            "device": parsed_ua['device']['family']})
        
        tax = int(req["tax"])
        if tax < 0 or tax > 30:
            return jsonify({"error": "Invalid Tax Category."}), 400
        try:
            cur.execute("""
            INSERT INTO tokens (
            token,
            sender_uuid,
            recipient_uuid,
            amount,
            tax,
            label,
            webhook_url,
            status,
            expires,
            ip_address,
            user_agent) VALUES
            (%s, %s, %s, %s, %s, %s, %s, 'issued', %s, %s, %s)""",(
            token,
            sender_uuid,
            req["recipient_uuid"],
            amount,
            tax,
            label,
            webhook,
            expires_at,
            request.remote_addr,
            ua_data))
        except Exception as e:
            logger.fatal("Saving Token failed")
            logger.debug(f"Traceback: {e}")
            return jsonify({"error": "Internal Server Error"}), 500
    return jsonify({"token": token, "expires": expires_at.isoformat()}), 201

@bp.route("/issue", methods=["POST"])
def issue_payment():
    """
    Executes a pre-authorized payment using a Single Pay Token.
    """
    logger.verbose("Payment is being issued via token...")
    req = request.get_json()
    
    if not req or "token" not in req:
        return jsonify({"error": "Missing token"}), 400
        
    token_str = req["token"]
    
    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
            # 1. Fetch token
            cur.execute("SELECT * FROM tokens WHERE token = %s FOR UPDATE", (token_str,))
            token_row = cur.fetchone()
            if not token_row:
                return jsonify({"error": "Token not found"}), 404
            
            token_data = cast(dict[str, Any], token_row)
            
            # 2. Check status and expiry
            if token_data["status"] != "issued":
                return jsonify({"error": "Token is not valid or already used"}), 400
                
            expires_at = Instant.from_timestamp(token_data["expires"].timestamp())
            if Instant.now() > expires_at:
                cur.execute("UPDATE tokens SET status = 'expired' WHERE token = %s", (token_str,))
                return jsonify({"error": "Token has expired"}), 400
                
            amount = Decimal(str(token_data["amount"])).quantize(Decimal("0.001"))
            if amount < Decimal("0.001"):
                return jsonify({"error": "Payment amount cannot be lower than 0.001"}), 400

            tax_category = str(token_data["tax"])
            sender_uuid = str(token_data["sender_uuid"])
            recipient_uuid = str(token_data["recipient_uuid"])
            
            # Tax calculation
            if tax_category == "1":
                tax = Decimal("0.300")
                tax_amount = (amount * tax).quantize(Decimal("0.001"))
                if tax_amount < Decimal("0.001"):
                    tax_amount = Decimal("0.001")
                final_amount = amount + tax_amount
            else:
                tax_amount = Decimal("0.000")
                final_amount = amount
                
            # 3. Retrieve Donor
            cur.execute("""
                SELECT b.id, b.balance, b.is_frozen, b.account_number,
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
                WHERE b.uuid = %s
                  AND b.is_deleted = 0
                LIMIT 1
            """, (sender_uuid,))
            donor_row = cur.fetchone()
            if not donor_row:
                return jsonify({"error": "Sender account not found"}), 404
            
            donor = cast(dict[str, Any], donor_row)
            if donor["balance"] < final_amount:
                return jsonify({"error": "Insufficient funds in sender account"}), 402
            
            donor_account_number = str(donor["account_number"])
            donor_holder = str(donor["holder"])
                
            # 4. Retrieve Recipient
            cur.execute("""
                SELECT b.id, b.is_frozen, b.account_number,
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
                WHERE b.uuid = %s
                  AND b.is_deleted = 0
                LIMIT 1
            """, (recipient_uuid,))
            receiver_row = cur.fetchone()
            if not receiver_row:
                return jsonify({"error": "Recipient account not found"}), 404
                
            receiver = cast(dict[str, Any], receiver_row)
            receiver_account_number = str(receiver["account_number"])
            receiver_holder = str(receiver["holder"])
            
            if donor["is_frozen"] or receiver["is_frozen"]:
                return jsonify({"error": "Account involved is frozen"}), 403
                
            # 5. Insert Primary Transaction
            description = token_data.get("label") or "SP Token Payment"
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
            
            # 6. Apply Balances
            cur.execute("UPDATE bank_accounts SET balance = balance - %s WHERE id = %s", (amount, donor["id"]))
            cur.execute("UPDATE bank_accounts SET balance = balance + %s WHERE id = %s", (amount, receiver["id"]))
            
            # 7. Apply Tax Transaction (if necessary)
            tax_id = ""
            if tax_amount > 0:
                tax = Decimal("0.300")
                gov_tax_account = 26
                tax_desc = f"30% Tax - ID: {transaction_id}"
                metadata = json.dumps({
                    "tax": str(tax), 
                    "tax_amount": str(tax_amount), 
                    "tax_category": tax_category, 
                    "transaction_id": transaction_id
                })
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
                """, ("tax", donor["id"], gov_tax_account, tax_amount, tax_category, tax_desc, metadata, 1))
                tax_id = cur.lastrowid
                cur.execute("UPDATE bank_accounts SET balance = balance - %s WHERE id = %s", (tax_amount, donor["id"]))
                cur.execute("UPDATE bank_accounts SET balance = balance + %s WHERE id = %s", (tax_amount, gov_tax_account))
            # 8. Mark Token as Used
            cur.execute("""
                UPDATE tokens 
                SET status = 'used', used_at = NOW() 
                WHERE token = %s
            """, (token_str,))
            
            webhook_url = token_data.get("webhook_url")
            
        finally:
            cur.close()
            
    # Webhook Logic (outside the DB transaction block but after it commits)
    if webhook_url:
        try:
            timestamp_iso = Instant.now().py_datetime().isoformat()
            is_discord = "discord.com/api/webhooks/" in webhook_url
            if is_discord:
                # Discord Rich Embed format
                payload = {
                    "embeds": [{
                        "title": "Payment Completed",
                        "color": 65280, # Green
                        "timestamp": timestamp_iso,
                        "fields": [
                            {"name": "Transaction ID", "value": str(transaction_id), "inline": True},
                            {"name": "Amount", "value": f"{amount} $", "inline": True},
                            {"name": "Tax Subtracted", "value": f"{tax_amount} $", "inline": True},
                            {"name": "Sender", "value": f"{donor_holder} ({donor_account_number})", "inline": False},
                            {"name": "Recipient", "value": f"{receiver_holder} ({receiver_account_number})", "inline": False},
                            {"name": "Label", "value": description, "inline": False}
                        ],
                        "footer": {"text": "LinePay - Provided by Albion InterCap"}
                    }]
                }
            else:
                # Custom generic JSON format
                payload = {
                    "status": "Payment Completed",
                    "transaction_id": transaction_id,
                    "amount": str(amount),
                    "tax_amount": str(tax_amount),
                    "description": description,
                    "sender_account_number": donor_account_number,
                    "sender_holder": donor_holder,
                    "recipient_account_number": receiver_account_number,
                    "recipient_holder": receiver_holder,
                    "timestamp": timestamp_iso
                }
            
            requests.post(webhook_url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Failed to trigger webhook for token {token_str}: {str(e)}")

    return jsonify({
        "success": True,
        "message": "Payment successful",
        "transaction_id": transaction_id,
        "tax_id": tax_id
    }), 200