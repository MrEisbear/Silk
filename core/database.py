from core.coreDB import DataBase
from core.logger import logger

try:
    db_helper = DataBase()
    engine = db_helper.engine
    db_session = db_helper.session
    get_session = db_helper.get_session
    logger.verbose("Database connection pool initialized!")
except RuntimeError:
    logger.fatal("Failed to initialize database helper!")
    exit(1)