import yaml

class CoreConfig:
    def __init__(self, path):
        with open(path, "r") as f:
            self.data = yaml.safe_load(f)

    def get(self, *keys, default=None):
        section = self.data
        for key in keys:
            if not isinstance(section, dict):
                return default
            section = section.get(key, default)
        return section
