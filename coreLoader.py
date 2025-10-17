meta = {
    "id": "CoreLoader",
    "name": "Core Loader",
    "version": "1.0.0",
    "depends": {
        "hard": {}, # Empty to follow convention.
        "soft": {} 
    }
}

# Very Shitty Loader here - Open for future impovement

import importlib.util
import os
import sys
import traceback
from ruamel.yaml import YAML
from dotenv import load_dotenv
from packaging import version  # for version comparison

# global tracker for loaded modules to prevent re-imports / loops
loaded_modules = {}

# ----------------------------
# ENV and CONFIG loading
# ----------------------------
load_dotenv()  # loads .env into os.environ

def load_config(path="config.yml"):
    if not os.path.isfile(path):
        return {}
    yaml_parser = YAML(typ="safe", pure=True)  # safe loader
    with open(path, "r") as f:
        return yaml_parser.load(f) or {}

# ----------------------------
# Import helpers
# ----------------------------
def import_module_from_path(path):
    """Imports a module from a given file path."""
    name = os.path.splitext(os.path.basename(path))[0]
    # avoid re-import
    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        return None

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None

# ----------------------------
# Dependency check
# ----------------------------
def check_dependencies(module, context):
    """Check hard and soft dependencies with version checks."""
    meta = getattr(module, "meta", None)
    logger = context["logger"]

    if not meta:
        logger.warning(f"Module {module} has no meta; skipping dependency check.")
        return True

    hard = meta.get("depends", {}).get("hard", {})
    soft = meta.get("depends", {}).get("soft", {})

    # Hard dependencies must exist and match version
    for dep_id, dep_ver in hard.items():
        dep_module = loaded_modules.get(dep_id)
        if not dep_module:
            logger.error(f"[{meta['name']}] Missing HARD dependency {dep_id} ({dep_ver})")
            return False
        # version check
        dep_module_ver = getattr(dep_module, "meta", {}).get("version", "0.0.0")
        if version.parse(dep_module_ver) < version.parse(dep_ver):
            logger.error(f"[{meta['name']}] HARD dependency {dep_id} version {dep_ver}+ required (found {dep_module_ver})")
            return False

    # Soft dependencies warning only
    for dep_id, dep_ver in soft.items():
        dep_module = loaded_modules.get(dep_id)
        if not dep_module:
            logger.warning(f"[{meta['name']}] Missing SOFT dependency {dep_id} ({dep_ver})")
            continue
        dep_module_ver = getattr(dep_module, "meta", {}).get("version", "0.0.0")
        if version.parse(dep_module_ver) < version.parse(dep_ver):
            logger.warning(f"[{meta['name']}] SOFT dependency {dep_id} version {dep_ver}+ recommended (found {dep_module_ver})")

    return True

# ----------------------------
# Module loader
# ----------------------------
def load_module(path, context):
    """Load a single module with dependency check and init."""
    module = import_module_from_path(path)
    logger = context["logger"]
    if not module:
        logger.error(f"Failed to import module from {path}")
        return None

    if not hasattr(module, "meta"):
        logger.warning(f"Module {path} missing meta; skipping")
        return None
    if not hasattr(module, "init"):
        logger.warning(f"Module {path} missing init(); skipping")
        return None
    
    # Skip if already loaded (prevents loops)
    if module.meta["id"] in loaded_modules:
        logger.info(f"Module {module.meta['name']} ({module.meta['id']}) already loaded, skipping")
        return loaded_modules[module.meta["id"]]

    # Check dependencies
    if not check_dependencies(module, context):
        logger.error(f"Module {module.meta['name']} skipped due to missing HARD dependencies")
        return None

    # Initialize module
    try:
        module.init(context)
        loaded_modules[module.meta["id"]] = module
        logger.info(f"Module {module.meta['name']} ({module.meta['id']}) loaded successfully")
        return module
    except Exception:
        logger.error(f"Module {module.meta['name']} failed during init:\n{traceback.format_exc()}")
        return None

# ----------------------------
# Folder loader
# ----------------------------
def load_all_from(folder, context):
    """Load all .py modules from a folder."""
    logger = context["logger"]
    if not os.path.isdir(folder):
        logger.warning(f"{folder} does not exist; skipping")
        return []

    excluded = {"core.py", "coreLoader.py"}

    modules = []
    for file in sorted(os.listdir(folder)):
        if file.endswith(".py") and not file.startswith("__") and file not in excluded:
            path = os.path.join(folder, file)
            mod = load_module(path, context)
            if mod:
                modules.append(mod)
    return modules

# ----------------------------
# Full context setup
# ----------------------------
def create_context(logger=None):
    if logger is None:
        from Modules.coreL import Logger
        logger = Logger("Core")

    context = {
        "logger": logger,
        "config": load_config("config.yml"),
        "env": os.environ,
        "modules": loaded_modules
    }
    return context
