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

# Startup Config
config = None
try:
    from coreC import Configure
    config = Configure("config.yml")
    logger.info("Config Started!")
except ModuleNotFoundError:
    logger.error("Config module not found!")
    logger.info("Using default Values...")

if config:
    level = config.get("environment", "log_level")
    print(level)
    logger.set_mode(level)

# Testing


logger.debug("Testing Debug...")
logger.verbose("Testing Verbose...")
logger.info("Testing Info...")
logger.warning("Testing Warning...")
logger.error("Testing Error...")
logger.fatal("Testing Fatal...")
exit()
