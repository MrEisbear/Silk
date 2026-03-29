# Code Implementation Guide: Treasury Account System

## 1. Updating `core/coreAuthUtil.py`
Add the `require_permission` decorator to facilitate permission-based access control. Ensure `from functools import wraps` and `from flask import jsonify` are available.

```python
def require_permission(permission_key: str):
    from functools import wraps
    from flask import jsonify
    from core.database import db_helper
    from core.logger import logger

    def decorator(func):
        @wraps(func)
        @require_token
        def wrapper(data, *args, **kwargs):
            user_uuid = data.get("uuid")
            with db_helper.cursor() as cur:
                cur.execute("""
                    SELECT 1 FROM user_jobs uj
                    JOIN job_permissions jp ON uj.job_id = jp.job_id
                    JOIN permissions p ON jp.permission_id = p.id
                    WHERE uj.user_uuid = %s AND p.permission_key = %s
                """, (user_uuid, permission_key))
                if not cur.fetchone():
                    logger.warning(f"User {user_uuid} missing permission: {permission_key}")
                    return jsonify({"error": f"Missing permission: {permission_key}"}), 403
            return func(data, *args, **kwargs)
        return wrapper
    return decorator
```

## 2. Updating `routes/transfer.py` for Tax Redirection
Modify the `make_payment` function to redirect collected taxes to the "Taxes" government account.

```python
# Within make_payment function (ensure Decimal and json are imported):
from decimal import Decimal
import simplejson as json

# ... inside the transaction block ...
match tax_category:
    case "1":
        tax_rate = Decimal("0.300")
        tax_amount = (amount * (1 + tax_rate)) - amount

        # Get the 'Taxes' government account ID
        cur.execute("SELECT id FROM bank_accounts WHERE account_number = 'G-TAXES' AND account_holder_type = 'gov'")
        tax_account_row = cur.fetchone()
        if tax_account_row:
            tax_account_id = tax_account_row["id"]

            # Record tax transaction
            description = f"30% Tax on Payment {transaction_id}"
            metadata = json.dumps({"tax": tax_rate, "tax_amount": tax_amount, "tax_category": tax_category, "transaction_id": transaction_id})

            cur.execute("""
                INSERT INTO transactions (
                    transaction_type, from_account_id, to_account_id, amount, description, metadata, confirmed
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, ("tax", donor["id"], tax_account_id, tax_amount, description, metadata, 1))

            # Update Taxes account balance
            cur.execute("UPDATE bank_accounts SET balance = balance + %s WHERE id = %s", (tax_amount, tax_account_id))
            cur.execute("UPDATE bank_accounts SET balance = balance - %s WHERE id = %s", (tax_amount, donor["id"]))
```

## 3. New Public Treasury Endpoints in `routes/Accounting.py`
Add public endpoints for viewing government account information and history.

```python
from flask import Blueprint, jsonify, request
from core.database import db_helper

# ... inside the Accounting blueprint ...

@bp.route("/public/gov/accounts", methods=["GET"])
def get_gov_accounts():
    with db_helper.cursor() as cur:
        cur.execute("SELECT uuid, account_number, balance FROM bank_accounts WHERE account_holder_type = 'gov'")
        return jsonify({"gov_accounts": cur.fetchall()}), 200

@bp.route("/public/gov/accounts/<uuid:account_uuid>/transactions", methods=["GET"])
def get_gov_account_history(account_uuid):
    account_uuid = str(account_uuid)
    with db_helper.cursor() as cur:
        cur.execute("SELECT id FROM bank_accounts WHERE uuid = %s AND account_holder_type = 'gov'", (account_uuid,))
        account = cur.fetchone()
        if not account:
             return jsonify({"error": "Government account not found"}), 404

        account_id = account["id"]
        cur.execute("""
            SELECT uuid, transaction_type, from_account_id, to_account_id, amount, created_at, description
            FROM transactions
            WHERE from_account_id = %s OR to_account_id = %s
            ORDER BY created_at DESC
        """, (account_id, account_id))
        return jsonify({"transactions": cur.fetchall()}), 200
```
