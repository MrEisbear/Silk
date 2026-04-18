from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token, require_permission
from core.cursorHelper import parse_cursor, create_cursor
from core.database import db_helper
from core.logger import logger
from typing import Any, cast
import os
from datetime import datetime
from decimal import Decimal
import simplejson as json

bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")

def get_account_ids(cur: Any, identifier: str) -> tuple[int, int, Decimal] | None:
    """Helper to resolve an account and return (id, account_holder_id, balance)."""
    if identifier.isdigit():
        col = "id"
    elif len(identifier) == 36 and "-" in identifier:
        col = "uuid"
    else:
        col = "account_number"
        
    cur.execute(f"SELECT id, account_holder_id, balance FROM bank_accounts WHERE {col} = %s", (identifier,))
    row = cur.fetchone()
    if not row:
        return None
        
    parse = cast(dict[str, Any], row)
    return int(parse["id"]), int(parse["account_holder_id"]), Decimal(str(parse["balance"]))

@bp.route("/statement/<string:bankaccount_id>/<int:year>/<int:month>", methods=["GET"])
@require_permission("bank.accounts.self.view.statement")
def get_statement(data: dict[str, Any], bankaccount_id: str, year: int, month: int):
    user_id = data.get("id")
    if not user_id:
        return {"error": "Unauthorized"}, 401

    # --- Validate date input early ---
    if month < 1 or month > 12:
        return {"error": "Invalid month"}, 400

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    with db_helper.cursor() as cur:
        # --- Ownership check (keep anti-enumeration behavior) ---
        ids = get_account_ids(cur, bankaccount_id)
        if not ids:
            return {"error": "Account not found"}, 404

        real_account_id, account_holder_id, current_balance = ids
        if account_holder_id != int(user_id):
            return {"error": "Account not found"}, 404

        # --- Main query (index-friendly + single pass) ---
        sql = """
        SELECT 
            t.id AS transaction_id,
            t.from_account_id,
            t.to_account_id,
            t.amount,
            t.transaction_type AS reason,
            t.description,
            t.confirmed AS is_success,
            t.created_at AS time,

            from_acc.account_number AS from_account_number,
            from_acc.account_holder_type AS from_holder_type,
            from_acc.account_holder_id AS from_holder_id,
            from_user.username AS from_username,

            to_acc.account_number AS to_account_number,
            to_acc.account_holder_type AS to_holder_type,
            to_acc.account_holder_id AS to_holder_id,
            to_user.username AS to_username

        FROM transactions t
        LEFT JOIN bank_accounts from_acc ON t.from_account_id = from_acc.id
        LEFT JOIN users from_user 
            ON from_acc.account_holder_type = 'user' 
           AND from_user.id = from_acc.account_holder_id

        LEFT JOIN bank_accounts to_acc ON t.to_account_id = to_acc.id
        LEFT JOIN users to_user 
            ON to_acc.account_holder_type = 'user' 
           AND to_user.id = to_acc.account_holder_id

        WHERE 
            (t.from_account_id = %(acc_id)s OR t.to_account_id = %(acc_id)s)
            AND t.created_at >= %(start)s
            AND t.created_at < %(end)s

        ORDER BY t.created_at DESC, t.id DESC;
        """

        cur.execute(sql, {
            "acc_id": real_account_id,
            "start": start,
            "end": end
        })

        rows = cast(list[dict[str, Any]], cur.fetchall())

        # --- Reconstruct Historical Balances ---
        # 1. Calculate the exact net flow that happened AFTER this month
        cur.execute("""
            SELECT SUM(amount) as future_in 
            FROM transactions 
            WHERE to_account_id = %(acc_id)s 
              AND created_at >= %(end)s 
              AND confirmed = 1
        """, {"acc_id": real_account_id, "end": end})
        row_future_in = cast(dict[str, Any], cur.fetchone() or {})
        future_in = Decimal(str(row_future_in.get("future_in") or 0))

        cur.execute("""
            SELECT SUM(amount) as future_out 
            FROM transactions 
            WHERE from_account_id = %(acc_id)s 
              AND created_at >= %(end)s 
              AND confirmed = 1
        """, {"acc_id": real_account_id, "end": end})
        row_future_out = cast(dict[str, Any], cur.fetchone() or {})
        future_out = Decimal(str(row_future_out.get("future_out") or 0))

        # 2. Starting from the live balance, remove all future flow mathematically to get our ending boundary
        ending_balance = current_balance - (future_in - future_out)

    # --- Domain mapping (kept OUT of SQL) ---
    GOV_ACCOUNT_NAMES = {
        "G-10091a4": "Allgemeine Staatskasse",
        "G-4003854": "Andere",
        "G-3006707": "Strafgelder",
        "G-200a869": "Steuern",
    }

    def resolve_owner(holder_type: str | None, account_number: str | None, username: str | None) -> str:
        if holder_type == "user":
            return username or "Unknown User"

        if holder_type == "company":
            return "Unknown Company"

        if holder_type == "gov":
            if account_number and account_number in GOV_ACCOUNT_NAMES:
                return GOV_ACCOUNT_NAMES[account_number]
            return "Regierung"

        return "System/External"

    # --- Post-processing + aggregation ---
    total_in = Decimal("0")
    total_out = Decimal("0")

    for r in rows:
        amount_raw = r.get("amount", 0)

        # normalize safely
        if isinstance(amount_raw, Decimal):
            amount = amount_raw
        else:
            amount = Decimal(str(amount_raw))

        is_success = bool(r.get("is_success"))

        if is_success:
            if str(r.get("to_account_id")) == str(real_account_id):
                total_in += amount
            elif str(r.get("from_account_id")) == str(real_account_id):
                total_out += amount

        # enrich response
        r["from_account_owner"] = resolve_owner(
            r.get("from_holder_type"),
            r.get("from_account_number"),
            r.get("from_username"),
        )

        r["to_account_owner"] = resolve_owner(
            r.get("to_holder_type"),
            r.get("to_account_number"),
            r.get("to_username"),
        )

        # optional: normalize amount to float for JSON
        r["amount"] = float(amount)

        # cleanup internal fields (keep response clean)
        del r["from_holder_type"]
        del r["from_holder_id"]
        del r["from_username"]
        del r["to_holder_type"]
        del r["to_holder_id"]
        del r["to_username"]

    # 3. Step back once more using the month's own flow to find its starting boundary!
    starting_balance = ending_balance - (total_in - total_out)

    now = datetime.now()
    is_incomplete = (year > now.year) or (year == now.year and month >= now.month)

    return jsonify({
        "statement_period": f"{year}-{month:02d}",
        "is_incomplete": is_incomplete,
        "summary": {
            "starting_balance": float(starting_balance),
            "total_in": float(total_in),
            "total_out": float(total_out),
            "ending_balance": float(ending_balance)
        },
        "transactions": rows
    }), 200

@bp.route("/recent/<string:bankaccount_id>", methods=["GET"])
@require_token
def get_recent_transactions(data: dict[str, int | str | bool], bankaccount_id: str):
    user_id: int | None = cast(int | None, data.get("id")) # Damn bro, I need a typed dict.
    if not user_id:
        return {"error":"Unauthorized"}, 401
    with db_helper.cursor() as cur:
        ids = get_account_ids(cur, bankaccount_id)
        if not ids:
            return {"error":"Account not found"}, 404
        
        real_account_id, account_holder_id, _ = ids
        if account_holder_id != int(user_id):
            return {"error":"Account not found"}, 404
        
        # We are now sure that the account exists and belongs to the user.
        cur.execute("""
        (SELECT * FROM transactions WHERE to_account_id = %s ORDER BY created_at DESC, id DESC LIMIT 25)
        UNION ALL
        (SELECT * FROM transactions WHERE from_account_id = %s ORDER BY created_at DESC, id DESC LIMIT 25)
        ORDER BY created_at DESC, id DESC
        LIMIT 25
        """, (real_account_id, real_account_id))
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
        ids = get_account_ids(cur, bankaccount_id)
        if not ids:
            return {"error":"Account not found"}, 404
        
        real_account_id, account_holder_id, _ = ids
        if account_holder_id != int(user_id):
            return {"error":"Account not found"}, 404
        
        # We are now sure that the account exists and belongs to the user.
        cur.execute("""
        (SELECT * FROM transactions WHERE to_account_id = %s AND (created_at, id) < (%s, %s)
        ORDER BY created_at DESC, id DESC LIMIT 50)
        UNION ALL
        (SELECT * FROM transactions WHERE from_account_id = %s AND (created_at, id) < (%s, %s)
        ORDER BY created_at DESC, id DESC LIMIT 50)
        ORDER BY created_at DESC, id DESC
        LIMIT 50""", (real_account_id, cursor_time, cursor_id, real_account_id, cursor_time, cursor_id))
        rows = cur.fetchall()
        
        next_cursor = None
        if rows:
            last_row = cast(dict[str, datetime | int | str], rows[-1])
            next_cursor = create_cursor(
                cast(datetime, last_row["created_at"]),
                cast(int, last_row["id"]),
            )
        return {"rows": rows, "next_cursor": next_cursor}, 200
        