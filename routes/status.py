"""
This module defines the status route for the API.
"""
from typing import Optional
from flask import Blueprint, abort
from flask.typing import ResponseReturnValue
from core.coreC import Configure
from core.logger import logger

bp = Blueprint("status", __name__, url_prefix="/api/status")

_cached_response: Optional[dict[str, str]] = None


def _init_status_cache() -> dict[str, str]:
    global _cached_response
    if _cached_response is None:
        try:
            config = Configure("config.yml")
            version = config.get_str("version")
            frontend_version = config.get_str("frontend_version")
            if version is None or frontend_version is None:
                logger.fatal("Config file is missing version or frontend_version!")
                raise RuntimeError("Invalid config.yml")
            _cached_response = {
                "latency": "Unknown",
                "version": str(version),
                "frontend_version": str(frontend_version),
            }
        except FileNotFoundError:
            logger.fatal("Config file not found; make sure config.yml exists!")
            raise
    return _cached_response


@bp.route("/", methods=["GET"])
def get_status() -> ResponseReturnValue:
    """
    Returns the current status of the API with sub-millisecond in-memory response.
    """
    try:
        data = _init_status_cache()
    except Exception:
        abort(500)

    logger.verbose("Status API called")
    return data, 200