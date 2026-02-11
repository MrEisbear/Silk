"""
This module defines the status route for the API.
"""
from flask import Blueprint, abort
from flask.typing import ResponseReturnValue
from core.coreC import Configure
from core.logger import logger

bp = Blueprint("status", __name__, url_prefix="/api/status")

@bp.route("/", methods=["GET"])
def get_status() -> ResponseReturnValue: 
    """
    Returns the current status of the API.
    """
    try:
        config = Configure("config.yml")
    except FileNotFoundError:
        logger.fatal("Config file not found; make sure config.yml exists!")
        abort(500)
    version: str | None = config.get_str("version")
    frontend_version: str | None = config.get_str("frontend_version")
    if version is None or frontend_version is None:
        logger.fatal("Config file is missing version or frontend_version!")
        abort(500)
    return {"latency": "Unknown",
            "version": str(version),
            "frontend_version": str(frontend_version)}, 200