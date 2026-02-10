"""
This module is used to get the version of the application.
"""
from core.coreC import Configure
from core.logger import logger

def get_version_internal() -> None:
    try:
        config = Configure("config.yml")
    except FileNotFoundError:
        logger.fatal("Config file not found; make sure config.yml exists!")
        return
    version: str | None = config.get_str("version")
    frontend_version: str | None = config.get_str("frontend_version")
    if version is None or frontend_version is None:
        logger.fatal("Config file is missing version or frontend_version!")
        return
    logger.info(f"Version: {version}")
    logger.info(f"Designed for Frontend Version: {frontend_version}")