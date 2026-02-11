from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from typing import Dict, Any, cast
from decimal import Decimal
from datetime import datetime, timedelta

bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")

@bp.route("/", methods=["GET"])
@require_token
def get_jobs(data):
    """
    Returns the user's jobs, their calculated highest salary class, 
    and the status of their daily claim.
    """
    user_id = data["id"] # Internal Int ID
    
    with db_helper.cursor() as cur:
        cur.execute("SELECT uuid, last_salary_claim FROM users WHERE id = %s", (user_id,))
        user_row = cur.fetchone()
        
        if not user_row:
            logger.error(f"User with id {user_id} not found tho Token exists?")
            return jsonify({"error": "User not found"}), 404
        user_row = cast(Dict[str, Any], user_row)
        user_uuid = user_row["uuid"]
        last_claim = user_row["last_salary_claim"]

        # 2. Get all jobs and their salary classes for this user
        # We join user_jobs -> jobs -> salary_classes
        cur.execute("""
            SELECT j.job_name, j.department, sc.class_level, sc.daily_amount
            FROM user_jobs uj
            JOIN jobs j ON uj.job_id = j.id
            JOIN salary_classes sc ON j.salary_class = sc.class_level
            WHERE uj.user_uuid = %s
            ORDER BY sc.daily_amount DESC
        """, (user_uuid,))
        
        jobs = cur.fetchall()

    # 3. Calculate Logic (Python side is often easier for MVPs than complex SQL)
    if not jobs:
        return jsonify({
            "jobs": [],
            "max_salary": 0,
            "max_class": 0,
            "can_claim": False,
            "next_claim_at": None
        }), 200
# Since we ordered by amount DESC, the first one is the highest
    max_salary_job = cast(Dict[str, Any], jobs[0])
    daily_pay = max_salary_job["daily_amount"]
    max_class = max_salary_job["class_level"]

    # 4. Check 24h Cooldown
    can_claim = True
    next_claim_time = None

    if last_claim:
        # Calculate when the 24h window expires
        cooldown_expires = last_claim + timedelta(hours=24)
        if datetime.now() < cooldown_expires:
            can_claim = False
            next_claim_time = cooldown_expires.isoformat()

    return jsonify({
        "jobs": jobs,
        "max_salary": daily_pay,
        "max_class": max_class,
        "can_claim": can_claim,
        "last_claim": last_claim.isoformat() if last_claim else None,
        "next_claim_at": next_claim_time
    }), 200

# This route is a contribution by Google
@bp.route("/claim", methods=["POST"])
@require_token
def claim_salary(data):
    user_id = data["id"]
    req = request.get_json()
    
    if not req or "account_id" not in req:
        return jsonify({"success": False, "message": "Missing account_id"}), 400
        
    target_account_uuid = req["account_id"]
    
    # Use a transaction to ensure atomicity
    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
            # 1. Verify User & Get Last Claim
            cur.execute("SELECT uuid, last_salary_claim FROM users WHERE id = %s FOR UPDATE", (user_id,))
            user_row = cur.fetchone()
            if not user_row:
                return jsonify({"success": False, "message": "User not found"}), 404
            
            user_row = cast(Dict[str, Any], user_row)
            user_uuid = user_row["uuid"]
            last_claim = user_row["last_salary_claim"]
            
            # 2. Check Cooldown
            if last_claim:
                cooldown_expires = last_claim + timedelta(hours=24)
                if datetime.now() < cooldown_expires:
                    return jsonify({
                        "success": False,
                        "message": "Cooldown active",
                        "cooldown": cooldown_expires.isoformat()
                    }), 403

            # 3. Calculate Salary Amount
            cur.execute("""
                SELECT sc.daily_amount, j.job_name, sc.class_level
                FROM user_jobs uj
                JOIN jobs j ON uj.job_id = j.id
                JOIN salary_classes sc ON j.salary_class = sc.class_level
                WHERE uj.user_uuid = %s
                ORDER BY sc.daily_amount DESC
                LIMIT 1
            """, (user_uuid,))
            
            job_row = cur.fetchone()
            if not job_row:
                 return jsonify({"success": False, "message": "Jobless"}), 400
                 
            job_row = cast(Dict[str, Any], job_row)
            salary_amount = job_row["daily_amount"]
            job_name = job_row["job_name"]
            class_level = job_row["class_level"]
            
            if salary_amount <= 0:
                 return jsonify({"success": False, "message": "Salary amount is zero or negative"}), 400

            # 4. Verify Target Account
            cur.execute("SELECT id, is_frozen, is_deleted FROM bank_accounts WHERE uuid = %s AND account_holder_id = %s", (target_account_uuid, user_id))
            account_row = cur.fetchone()
            
            if not account_row:
                return jsonify({"success": False, "message": "Account not found or not owned by user"}), 404
            
            account_row = cast(Dict[str, Any], account_row)
            if account_row["is_frozen"]:
                return jsonify({"success": False, "message": "Account is frozen"}), 403
            
            if account_row.get("is_deleted", 0):
                return jsonify({"success": False, "message": "Account not found or not owned by user"}), 404
                # check if account is deleted but not tell the user that its deleted to not expose potentially sensitive data
            internal_account_id = account_row["id"]

            # 5. Execute Updates
            # Update User Last Claim
            cur.execute("UPDATE users SET last_salary_claim = NOW() WHERE id = %s", (user_id,))
            
            import simplejson as json
            metadata = json.dumps({
                "job_name": job_name,
                "class_level": class_level
            })
            
            # Log Transaction
            # TODO: Add withdrawal from Treasury account in the future
            cur.execute("""
                INSERT INTO transactions (
                    transaction_type, 
                    to_account_id, 
                    amount, 
                    description,
                    metadata,
                    confirmed, 
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, ('salary', internal_account_id, salary_amount, 'Salary Payment', metadata, 1))
            
            transaction_id = cur.lastrowid
            
            # Update Balance
            cur.execute("UPDATE bank_accounts SET balance = balance + %s WHERE id = %s", (salary_amount, internal_account_id))
            
            logger.verbose(f"User {user_id} claimed salary {salary_amount} to account {target_account_uuid}")
            
        except Exception as e:
            logger.error(f"Salary claim failed for user {user_id}: {e}")
            raise e # Reraise to trigger rollback
            
    return jsonify({
        "success": True, 
        "amount": salary_amount,
        "transaction_id": transaction_id
    }), 200
