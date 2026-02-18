from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token
from core.cursorHelper import parse_cursor, create_cursor
from core.database import db_helper
from core.logger import logger
from typing import Any, cast
import os
from datetime import datetime
from decimal import Decimal
import simplejson as json

bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")

@bp.route("/recent/<string:bankaccount_id>", methods=["GET"])
@require_token
def get_recent_transactions(data: dict[str, int | str | bool], bankaccount_id: str):
    user_id: int | None = cast(int | None, data.get("id")) # Damn bro, I need a typed dict.
    if not user_id:
        return {"error":"Unauthorized"}, 401
    with db_helper.cursor() as cur:
        cur.execute("SELECT account_holder_id FROM bank_accounts WHERE id = %s", (bankaccount_id,))
        row = cur.fetchone()
        if not row:
            return {"error":"Account not found"}, 404
        parse = cast(dict[str, int | str | bool], row)
        if int(parse["account_holder_id"]) != int(user_id):
            return {"error":"Account not found"}, 404
        
        # We are now sure that the account exists and belongs to the user.
        cur.execute("""
        (SELECT * FROM transactions WHERE to_account_id = %s ORDER BY created_at DESC, id DESC LIMIT 25)
        UNION ALL
        (SELECT * FROM transactions WHERE from_account_id = %s ORDER BY created_at DESC, id DESC LIMIT 25)
        ORDER BY created_at DESC, id DESC
        LIMIT 25
        """, (bankaccount_id, bankaccount_id))
        rows = cur.fetchall()
        return {"rows": rows}, 200

@bp.route("/history/<string:bankaccount_id>", methods=["GET"])
@require_token
def get_history(data: dict[str, int | str | bool], bankaccount_id: str):
    user_id: int | None = cast(int | None, data.get("id")) # Damn bro, I need a typed dict.
    if not user_id:
        return {"error":"Unauthorized"}, 401

    cursor_str = request.args.get("cursor")
    cursor_time, cursor_id = parse_cursor(cursor_str)
    if not cursor_time or not cursor_id:
        cursor_time = '9999-12-31 23:59:59'
        cursor_id = 999999999

    with db_helper.cursor() as cur:
        cur.execute("SELECT account_holder_id FROM bank_accounts WHERE id = %s", (bankaccount_id,))
        row = cur.fetchone()
        if not row:
            return {"error":"Account not found"}, 404
        parse = cast(dict[str, int | str | bool], row)
        if int(parse["account_holder_id"]) != int(user_id):
            return {"error":"Account not found"}, 404
        
        # We are now sure that the account exists and belongs to the user.
        cur.execute("""
        (SELECT * FROM transactions WHERE to_account_id = %s AND (created_at, id) < (%s, %s)
        ORDER BY created_at DESC, id DESC LIMIT 50)
        UNION ALL
        (SELECT * FROM transactions WHERE from_account_id = %s AND (created_at, id) < (%s, %s)
        ORDER BY created_at DESC, id DESC LIMIT 50)
        ORDER BY created_at DESC, id DESC
        LIMIT 50""", (bankaccount_id, cursor_time, cursor_id, bankaccount_id, cursor_time, cursor_id))
        rows = cur.fetchall()
        
        next_cursor = None
        if rows:
            last_row = cast(dict[str, datetime | int | str], rows[-1])
            next_cursor = create_cursor(
                cast(datetime, last_row["created_at"]),
                cast(int, last_row["id"]),
            )
        return {"rows": rows, "next_cursor": next_cursor}, 200
        