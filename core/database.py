from core.coreDB import DataBase
from core.logger import logger
try:
    db_helper = DataBase()
    logger.verbose("Databse connection initialized!")
except RuntimeError:
    exit(1)