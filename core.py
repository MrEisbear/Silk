from coreLoader import load_all_from, create_context

context = create_context()
logger = context["logger"]

logger.info("Booting Silk Core...")

# Load core modules first
load_all_from(".", context)

# Load plugins
load_all_from("./plugins", context)

logger.info("Silk started successfully!")
