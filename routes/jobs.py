from flask import Blueprint, jsonify, request
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from typing import Dict, Any, cast
from decimal import Decimal
from datetime import datetime, timedelta

bp_jobs = Blueprint("jobs", __name__, url_prefix="/api/jobs")

@bp_jobs.route("/", methods=["GET"])
@require_token
def geta_jobs(data):
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
