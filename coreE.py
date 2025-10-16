__module__ = "Silk Errors"
__version__ = "0.0.1"

class NotFound(Exception):
    pass

class MissingImport(Exception):
    pass
    @staticmethod
    def raise_MissingImport(module: str, dependency: str):
        raise MissingImport(f"[{module}] Missing dependency: {dependency}")

class FatalError(Exception):
    pass

class CoreError(Exception):
    pass

class IntegrityError(Exception):
    pass
