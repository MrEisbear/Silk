from flask import Blueprint, redirect, request, jsonify
from core.coreAuthUtil import hash_password, check_password, create_jwt, require_token, hash_pin, check_pin
from core.database import db_helper
from whenever import Instant, minutes
from core.logger import logger
from typing import cast, Dict, Any, Tuple, Callable
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
        amount = Decimal(amount)
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
        sender = cast(Dict[str, Any], row)
        if sender["pin_locked_until"] is not None:
            now = Instant.now()
            if now.py_datetime() < sender["pin_locked_until"]:
                return jsonify({"error": "Account is locked"}), 403
        if not sender["pin_hash"]:
            return jsonify({"error": "PIN not set"}), 400
        if not check_pin(pin, sender["uuid"], sender["pin_hash"]):
            attempts = sender["pin_failed_attempts"] + 1
            if attempts >= 3:
                cur.execute("UPDATE bank_accounts SET pin_locked_until = DATE_ADD(NOW(), INTERVAL 15 MINUTES) WHERE uuid = %s", (sender["uuid"],))
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
        reciever = cast(Dict[str, Any], row)
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
                logger.fatal(e)
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
            req["tax"],
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