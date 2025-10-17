meta = {
    "id": "CoreLoader",
    "name": "Core Loader",
    "version": "1.0.0",
    "depends": {
        "hard": {}, # Empty to follow convention.
        "soft": {} 
    }
}

# Shitty Loader here - Open for future impovement

import importlib.util
import os
import sys
import traceback

loaded_modules = {}

def import_module_from_path(path):
    """Imports a module from a given file path."""
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None

def check_dependencies(module, context):
    """Check hard and soft dependencies."""
    meta = getattr(module, "meta", None)
    logger = context["logger"]

    if not meta:
        logger.warning(f"Module {module} has no meta; skipping dependency check.")
        return True

    hard = meta.get("depends", {}).get("hard", {})
    soft = meta.get("depends", {}).get("soft", {})

    # Hard dependencies must exist
    for dep, ver in hard.items():
        if dep not in loaded_modules:
            logger.error(f"[{meta['name']}] Missing HARD dependency {dep} ({ver})")
            return False

    # Soft dependencies warning only
    for dep, ver in soft.items():
        if dep not in loaded_modules:
            logger.warning(f"[{meta['name']}] Missing SOFT dependency {dep} ({ver})")

    return True

def load_module(path, context):
    """Load a single module with dependency check and init."""
    module = import_module_from_path(path)
    logger = context["logger"]
    if not module:
        logger.error(f"Failed to import module from {path}")
        return None

    if not hasattr(module, "meta") or not hasattr(module, "init"):
        logger.warning(f"Module {path} missing meta or init(); skipping")
        return None

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

def load_all_from(folder, context):
    """Load all .py modules from a folder."""
    logger = context["logger"]
    if not os.path.isdir(folder):
        logger.warning(f"{folder} does not exist; skipping")
        return []

    modules = []
    for file in sorted(os.listdir(folder)):
        if file.endswith(".py") and not file.startswith("__"):
            path = os.path.join(folder, file)
            mod = load_module(path, context)
            if mod:
                modules.append(mod)
    return modules
