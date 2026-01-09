import secrets

def generate_account_number(prefix: str, cur, max_attempts=5):
    for _ in range(max_attempts):
        accnum = prefix + secrets.token_hex(4)
        cur.execute(
            "SELECT 1 FROM bank_accounts WHERE account_number = %s",
            (accnum,)
        )
        if not cur.fetchone():
            return accnum
    raise RuntimeError("Failed to generate unique account number")
