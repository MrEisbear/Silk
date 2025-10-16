# Startup Logger
try:
    from coreL import Logger
except ModuleNotFoundError:
    print("\033[1;31m[FATAL] [Core] Logger module not found!\033[0m")
    exit(1)
logger = Logger("Core")
logger.info("Logger Started!")

# Check Version of Logger
try:
    from coreQ import Version
    try:
        if not Version.check_ver(logger.version(), "1.0.0"):
            logger.warning("Old logger version detected!")
    except ValueError:
        logger.warning("Logger may be outdated or broken, did not provide Version!")
except ModuleNotFoundError:
    logger.error("Versioning module not found!")

# Startup Config
config = None
try:
    from coreE import *
    try:
        from coreC import Configure
        config = Configure("config.yml")
        logger.info("Config Started!")
    except ModuleNotFoundError:
        logger.error("Config module not found!")
        logger.info("Using default Values...")
    except MissingImport:
        logger.error(MissingImport)
except ModuleNotFoundError:
    logger.fatal("Error Module not found!")
    exit(1)

# Try to set logger level based on config, if no config default to info
if config:
    level = config.get("environment", "log_level")
    logger.set_mode(level)
else:
    logger.set_mode("INFO")
logger.info(f"Logger Level Set to {logger.mode}")

# At this point the core should be ready to start the plugins?