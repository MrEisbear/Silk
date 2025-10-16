from ruamel.yaml import YAML # type: ignore

class Configure:
    def __init__(self, path):
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
