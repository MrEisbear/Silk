# Core Authentication

from flask import Blueprint, request, jsonify
from core.coreAuthUtil import hash_password, check_password, create_jwt
from main import logger, db_helper
from typing import cast, Dict, Any

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

@bp.route("/register", methods=["POST"])
def register():
    logger.verbose("Registering new user...")
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not password:
        logger.verbose("Register failed due to missing data; 400")
        return jsonify({"error": "Missing username or password"}), 400

    with db_helper.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username=%s OR email=%s", (username, email))
        if cur.fetchone():
            return jsonify({"error": "User already exists"}), 409

        cur.execute("""
            INSERT INTO users (uuid, username, email, password_hash, manual)
            VALUES (UUID(), %s, %s, %s, TRUE)
        """, (username, email, hash_password(password)))
    

    return jsonify({"success": True, "message": "Registered successfully!"}), 201


@bp.route("/login", methods=["POST"])
def login():
    logger.verbose("Login API called...")
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    with db_helper.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE username=%s", (username,))
        user = cur.fetchone()
        user = cast(Dict[str, Any], user) if user else None

        if not user or not check_password(password, user["password_hash"]):
            logger.verbose("Login failed due to invalid credentials; 401")
            return jsonify({"error": "Invalid credentials"}), 401

        token = create_jwt(user["id"])
        logger.verbose("Logged user with id " + str(user["id"]) + "in!")
    return jsonify({"token": token})

