from ruamel.yaml import YAML # type: ignore

class Configure:
    def __init__(self, path):
        self.yaml = YAML(typ='safe')
        with open(path, "r") as f:
            self.data = self.yaml.load(f)

    def get(self, key, default=None):
        return self.data.get(key, default)
