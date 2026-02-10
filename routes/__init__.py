import importlib
import pkgutil
from flask import Blueprint
from core.logger import logger

def register_blueprints(app):
    package_name = __name__
    package = importlib.import_module(package_name)

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg:
            continue
        module = importlib.import_module(f"{package_name}.{module_name}")

        bp = getattr(module, "bp", None)
        if isinstance(bp, Blueprint):
            app.register_blueprint(bp)
            logger.verbose(f"Registered blueprint: {module_name}")

def initStatus():
    try:
        from core.coreS import get_version_internal
    except (ImportError, ModuleNotFoundError):
        logger.error("Failed to show Status. Is StatusModule installed?")
        return
    get_version_internal()
    return