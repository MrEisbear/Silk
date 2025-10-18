from core.coreL import Logger
from ruamel.yaml import YAML
from core.coreC import Configure

logger = Logger("Silk")
try:
    config = Configure("config.yml")
except FileNotFoundError:
    logger.fatal("Config file not found; make sure config.yml exists!")
    exit(1)


logger.set_mode(config.get("environment", "log_level"))
