meta = {
    "id": "Core",
    "name": "Silk Core",
    "version": "1.0.0",
    "depends": {
        "hard": {},
        "soft": {}
    }
}

# Boot
from coreLoader import load_all_from, create_context
context = create_context()
logger = context["logger"].get_child(meta["name"])
logger.info("Booting Silk Core...")
# Load core modules first
load_all_from("./Modules", context)
# Load pluginso
logger.info("Loading plugins...")
load_all_from("./Plugins", context)