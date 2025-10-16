__part__ = "Silk Config"
__version__ = "1.0.0"

class Configure:
    def __init__(self, path):
        try:
            from ruamel.yaml import YAML
            self.yaml = YAML(typ='safe')
        except ModuleNotFoundError:
            try:
                from coreE import MissingImport
                MissingImport.raise_MissingImport(__part__, "ruamel.yaml")
            except ModuleNotFoundError:
                raise ModuleNotFoundError

        with open(path, "r") as f:
            self.data = self.yaml.load(f)

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            value = value.get(key)
            if value is None:
                return default
        return value
