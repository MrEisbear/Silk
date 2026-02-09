import sys
import os
import secrets
import string
import json
from decimal import Decimal
from datetime import timezone
from whenever import Instant, hours

# Add root directory to sys.path to import core modules
# The script is in /home/SilkC/scripts/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, g
from dotenv import load_dotenv
# Load environment variables from root .env before other imports
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from core.database import db_helper

def gen_giftcode(length=16):
    # Generates a string of random digits (matches giftcards.py)
    return ''.join(secrets.choice(string.digits) for _ in range(length))

def main():
    if len(sys.argv) < 2:
        print("Usage: giftcard.sh <amount>")
        sys.exit(1)

    try:
        # Support both . and , as decimal separators if needed, but Decimal usually wants .
        amount_str = sys.argv[1].replace(',', '.')
        amount = Decimal(amount_str)
    except Exception:
        print(f"Error: Invalid amount '{sys.argv[1]}'. Please provide a numeric value.")
        sys.exit(1)

    if amount <= 0:
        print("Error: Amount must be greater than 0.")
        sys.exit(1)

    # Use Flask app context because db_helper uses flask.g
    app = Flask(__name__)
    with app.app_context():
        code = gen_giftcode()
        # Set expiration to 1 year (following routes/giftcards.py logic)
        expires_at = Instant.now() + hours(365 * 24)
        expires_at_dt = expires_at.py_datetime()
        
        metadata = {
            "code": code,
            "expires": expires_at_dt.isoformat(),
            "provider": "Administrator",
            "issued_via": "CLI"
        }
        
        try:
            with db_helper.transaction() as db:
                cur = db.cursor(dictionary=True)
                
                # Optional: insert a transaction record to keep track of this issuance
                # But since it's "Administrator", we don't have a from_account_id.
                # We'll stick to inserting the gift_code as requested.
                
                cur.execute("""
                    INSERT INTO gift_codes (
                        code,
                        amount,
                        created_by,
                        expires_at,
                        is_active
                    ) VALUES (%s, %s, %s, %s, %s)
                """, (code, amount, "Administrator", expires_at_dt, 1))
                
                print("\n" + "="*40)
                print("   GIFT CARD ISSUED SUCCESSFULLY")
                print("="*40)
                print(f"Code:   {code}")
                print(f"Amount: {amount}")
                print(f"Expiry: {expires_at_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                print("="*40 + "\n")
                
        except Exception as e:
            print(f"Error executing database transaction: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
