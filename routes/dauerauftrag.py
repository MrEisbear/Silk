from flask import Blueprint, request
from core.coreAuthUtil import require_token
from core.database import db_helper
from core.logger import logger
from core.limiter import limiter

bp = Blueprint("dauerauftrag", __name__, url_prefix="/v1/bank/accounts/")

@bp.route("/<string:bankaccount_uuid>/recurring", methods=["POST"])
@limiter.limit("5 per minute")
@require_token
def create_recurring_transaction(data, bankaccount_uuid: str):
    user_id = data["id"]
    req = request.get_json()
    
    if not req or not all(k in req for k in ("targetAccountUuid", "amount", "reference", "interval")):
        return {"error": "Missing required fields"}, 400
        