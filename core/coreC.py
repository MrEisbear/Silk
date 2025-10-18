__part__ = "Silk Config"
__version__ = "1.0.0"

# Core Config Module

class Configure:
    def __init__(self, path):
        from ruamel.yaml import YAML
        self.yaml = YAML(typ='safe')

        with open(path, "r") as f:
            self.data = self.yaml.load(f)

    def get(self, *keys, default=None):
        value = self.data
        for key in keys:
            value = value.get(key)
            if value is None:
                return default
        return value