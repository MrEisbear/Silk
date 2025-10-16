# Startup Logger
try:
    from coreL import Logger
except ModuleNotFoundError:
    print("\033[1;31m[FATAL] [Core] Logger module not found!\033[0m")
    exit()
logger = Logger("Core")
logger.info("Logger Started!")

logger_ver = float(logger.version()) #Checks 
if logger_ver < 0.1:
    logger.warning("Old Logger Version detected!")

#
try:
    from coreC import Configure
except ModuleNotFoundError:
    logger.error("Config module not found!")
    logger.info("Using default Values...")

