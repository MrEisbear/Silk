from flask import Blueprint, jsonify
from core.database import db_helper
from typing import Any, cast
from datetime import datetime
import simplejson as json

bp = Blueprint("v2_transaction", __name__, url_prefix="/api/v2/")

@bp.route("/transaction/<int:transaction_id>", methods=["GET"])
def get_transaction(transaction_id: int):
    with db_helper.cursor() as cur:
        # Get the transaction with joined sender and receiver account numbers
        sql = """
            SELECT 
                t.id, t.uuid, t.transaction_type, t.amount, t.tax_category, 
                t.description, t.metadata, t.confirmed, t.created_at,
                from_acc.account_number as sender_acc_num,
                to_acc.account_number as receiver_acc_num
            FROM transactions t
            LEFT JOIN bank_accounts from_acc ON t.from_account_id = from_acc.id
            LEFT JOIN bank_accounts to_acc ON t.to_account_id = to_acc.id
            WHERE t.id = %s
        """
        cur.execute(sql, (transaction_id,))
        row = cur.fetchone()
        
        if not row:
            return jsonify({"error": "Transaction not found"}), 404
            
        row = cast(dict[str, Any], row)
        
        tax_amount = None
        tax_transaction_id = None
        
        # If this is a tax transaction itself, its tax amount is its amount
        if row["transaction_type"] == "tax":
            tax_amount = float(row["amount"])
            tax_transaction_id = str(row["id"])
        else:
            # Check if this main transaction has an associated tax transaction
            tax_sql = """
                SELECT id, amount 
                FROM transactions 
                WHERE transaction_type = 'tax' 
                AND JSON_EXTRACT(metadata, '$.transaction_id') = %s 
                LIMIT 1
            """
            cur.execute(tax_sql, (transaction_id,))
            tax_row = cur.fetchone()
            if tax_row:
                tax_row = cast(dict[str, Any], tax_row)
                tax_amount = float(tax_row["amount"])
                tax_transaction_id = str(tax_row["id"])

        # Format the transaction_type to match the C# Enum (e.g. 'Transfer', 'Payment')
        trans_type_db = str(row["transaction_type"])
        trans_type = trans_type_db.capitalize()
            
        metadata_str = row["metadata"]
        if isinstance(metadata_str, bytes):
            metadata_str = metadata_str.decode('utf-8')
            
        created_at = row["created_at"]
        iso_time = created_at.isoformat() + "Z" if isinstance(created_at, datetime) else None

        response = {
            "UUID": str(row["uuid"]),
            "TransactionID": str(row["id"]),
            "TransactionType": trans_type,
            "CreationDate": iso_time,
            "ValueDeliveryTime": iso_time,
            "Amount": float(row["amount"]),
            "SenderBankAccountNumber": row["sender_acc_num"] or "",
            "ReceiverBankAccountNumber": row["receiver_acc_num"] or "",
            "Metadata": metadata_str,
            "Description": row["description"],
            "TaxCategory": int(row["tax_category"]) if row["tax_category"] is not None else None,
            "TaxAmount": tax_amount,
            "TaxTransactionID": tax_transaction_id,
            "Confirmed": bool(row["confirmed"])
        }
        
        return jsonify(response), 200
