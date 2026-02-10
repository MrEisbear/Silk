# ruff: noqa
from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token, require_role
from core.database import db_helper
from core.logger import logger
from typing import Dict, Any, cast
import secrets
import string
import json
from whenever import Instant, hours
from decimal import Decimal

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

# --- UTILS ---
def gen_giftcode(length=16):
    return ''.join(secrets.choice(string.digits) for _ in range(length))

# --- MODERATION ROUTES (Users & Giftcards) ---

@bp.route("/giftcards", methods=["POST"])
@require_role("mod") 
def create_system_giftcard(data):
    """
    Creates a gift card from the 'system'.
    Allows mods to issue rewards without deducting from a user account.
    """
    admin_id = data["id"]
    req = request.get_json()
    
    if not req or "amount" not in req:
        return jsonify({"error": "Missing amount"}), 400
        
    amount = req["amount"]
    amount = req["amount"]
    try:
        amount = Decimal(str(amount))
        if amount <= 0: raise ValueError
    except (ValueError, TypeError, ArithmeticError):
        return jsonify({"error": "Invalid amount"}), 400

    code = gen_giftcode()
    expires_at = Instant.now().add(hours=365 * 24).py_datetime()
     
    # For system giftcards, created_by can be the admin's ID, but we need to ensure 
    # it doesn't try to deduct balance. 
    # We will use a special marker or just not run the update balance query.
    
    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
             # We link it to the admin who created it for audit logs
             # But we DONT deduct money from them.
             cur.execute("""
                INSERT INTO gift_codes (
                    code, amount, created_by, expires_at, is_active
                ) VALUES (%s, %s, %s, %s, 1)
             """, (code, amount, admin_id, expires_at))
             
             logger.verbose(f"Admin/Mod {admin_id} created system giftcard {code} worth {amount}")
             
        except Exception as e:
            logger.error(f"Failed to create system giftcard: {e}")
            raise e

    return jsonify({
        "success": True,
        "code": code,
        "amount": amount
    }), 201


@bp.route("/users/<int:user_id>/jobs", methods=["GET"])
@require_role("mod")
def get_user_jobs(data, user_id):
    """View jobs assigned to a specific user"""
    with db_helper.cursor() as cur:
        # Get user UUID first
        cur.execute("SELECT uuid, username FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
             return jsonify({"error": "User not found"}), 404
        
        user_uuid = user["uuid"]

        # Fetch jobs
        cur.execute("""
            SELECT j.id, j.job_name, j.department, sc.class_level, sc.daily_amount
            FROM user_jobs uj
            JOIN jobs j ON uj.job_id = j.id
            JOIN salary_classes sc ON j.salary_class = sc.class_level
            WHERE uj.user_uuid = %s
        """, (user_uuid,))
        jobs = cur.fetchall()
        
    return jsonify({"username": user["username"], "jobs": jobs}), 200


@bp.route("/users/<int:user_id>/jobs", methods=["POST"])
@require_role("mod")
def assign_user_job(data, user_id):
    """Assign a job to a user"""
    req = request.get_json()
    if not req or "job_id" not in req:
        return jsonify({"error": "Missing job_id"}), 400
        
    job_id = req["job_id"]
    
    with db_helper.cursor() as cur:
        # Get user UUID
        cur.execute("SELECT uuid FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
             return jsonify({"error": "User not found"}), 404
        user_uuid = user["uuid"]
        
        # Verify Job exists
        cur.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
        if not cur.fetchone():
             return jsonify({"error": "Job not found"}), 404
             
        # Check if already assigned
        cur.execute("SELECT 1 FROM user_jobs WHERE user_uuid = %s AND job_id = %s", (user_uuid, job_id))
        if cur.fetchone():
             return jsonify({"error": "User already has this job"}), 409
             
        # Assign
        cur.execute("INSERT INTO user_jobs (user_uuid, job_id) VALUES (%s, %s)", (user_uuid, job_id))
        
    logger.verbose(f"Mod {data['id']} assigned job {job_id} to user {user_id}")
    return jsonify({"success": True, "message": "Job assigned"}), 201


@bp.route("/users/<int:user_id>/jobs/<int:job_id>", methods=["DELETE"])
@require_role("mod") # Assuming mods can also remove jobs
def remove_user_job(data, user_id, job_id):
    """Remove a job from a user"""
    with db_helper.cursor() as cur:
        cur.execute("SELECT uuid FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
             return jsonify({"error": "User not found"}), 404
        user_uuid = user["uuid"]
        
        cur.execute("DELETE FROM user_jobs WHERE user_uuid = %s AND job_id = %s", (user_uuid, job_id))
        if cur.rowcount == 0:
             return jsonify({"error": "Job assignment not found"}), 404
             
    logger.verbose(f"Mod {data['id']} removed job {job_id} from user {user_id}")
    return jsonify({"success": True, "message": "Job removed"}), 200

# --- ADMIN ROUTES (Balance, Data Mangement) ---

@bp.route("/users/<int:user_id>/balance", methods=["POST"])
@require_role("admin")
def adjust_balance(data, user_id):
    """
    Directly adjust a user's account balance.
    Can be positive (deposit) or negative (withdraw).
    """
    admin_id = data["id"]
    req = request.get_json()
    
    if not req or "amount" not in req:
        return jsonify({"error": "Missing amount"}), 400
    
    # Optional: specify which account to target if user has multiple (default to first found/active)
    account_uuid = req.get("account_uuid") 
    
    amount = req["amount"]
    amount = req["amount"]
    try:
        amount = Decimal(str(amount))
    except (ValueError, TypeError, ArithmeticError):
        return jsonify({"error": "Invalid amount"}), 400
        
    reason = req.get("reason", "Admin Adjustment")

    with db_helper.transaction() as db:
        cur = db.cursor(dictionary=True)
        try:
            # Find target account
            query = "SELECT id, balance FROM bank_accounts WHERE account_holder_id = %s"
            params = [user_id]
            
            if account_uuid:
                query += " AND uuid = %s"
                params.append(account_uuid)
            
            query += " LIMIT 1 FOR UPDATE"
            
            cur.execute(query, tuple(params))
            account = cur.fetchone()
            
            if not account:
                return jsonify({"error": "User has no bank account"}), 404
                
            acc_id = account["id"]
            new_balance = Decimal(str(account["balance"])) + amount
            
            if new_balance < 0:
                 return jsonify({"error": "Insufficient funds for deduction"}), 400

            # Update Balance
            cur.execute("UPDATE bank_accounts SET balance = balance + %s WHERE id = %s", (amount, acc_id))
            
            # Log Transaction
            cur.execute("""
                INSERT INTO transactions (
                    transaction_type, to_account_id, amount, confirmed, description, metadata, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, ('admin_adj', acc_id, amount, 1, reason, json.dumps({"admin_id": admin_id})))
            
            logger.verbose(f"Admin {admin_id} adjusted balance for user {user_id} by {amount}")
            
        except Exception as e:
            logger.error(f"Balance adjustment failed: {e}")
            raise e
            
    return jsonify({"success": True, "new_balance": new_balance}), 200


@bp.route("/users/<int:user_id>", methods=["DELETE"])
@require_role("admin")
def delete_user(data, user_id):
    """
    Soft delete or ban a user.
    """
    admin_id = data["id"]
    if user_id == admin_id:
        return jsonify({"error": "Cannot delete yourself"}), 400
        
    with db_helper.cursor() as cur:
        # We might want to just set is_banned = 1 or is_deleted = 1 if those columns exist
        # Checking users table schema from previous knowledge (no strict schema file)
        # Assuming we can just BAN them for now if 'is_banned' exists. 
        # routes/Users.py uses 'is_banned = 0' in queries, so it exists.
        
        cur.execute("UPDATE users SET is_banned = 1 WHERE id = %s", (user_id,))
        if cur.rowcount == 0:
             return jsonify({"error": "User not found"}), 404
             
    logger.verbose(f"Admin {admin_id} banned user {user_id}")
    return jsonify({"success": True, "message": "User banned"}), 200


@bp.route("/jobs", methods=["POST"])
@require_role("admin")
def create_job_definition(data):
    """Create a new Job definition globally"""
    req = request.get_json()
    required = ["job_name", "department", "salary_class"]
    if not req or not all(k in req for k in required):
        return jsonify({"error": f"Missing fields. Required: {required}"}), 400
        
    with db_helper.cursor() as cur:
        # Check if salary class exists
        cur.execute("SELECT 1 FROM salary_classes WHERE class_level = %s", (req["salary_class"],))
        if not cur.fetchone():
             return jsonify({"error": "Salary class does not exist"}), 400
             
        cur.execute("""
            INSERT INTO jobs (job_name, department, salary_class)
            VALUES (%s, %s, %s)
        """, (req["job_name"], req["department"], req["salary_class"]))
        
        new_id = cur.lastrowid
        
    logger.verbose(f"Admin {data['id']} created job {req['job_name']}")
    return jsonify({"success": True, "id": new_id, "message": "Job created"}), 201
