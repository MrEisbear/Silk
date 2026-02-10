from typing import Any
from collections.abc import MutableMapping
from ruamel.yaml import YAML

__part__ = "Silk Config"
__version__ = "1.0.0"


class Configure:
    def __init__(self, path: str) -> None:
        yaml = YAML(typ="safe")
        with open(path, "r") as f:
            self.data: MutableMapping[str, Any] = yaml.load(f)

    def get(self, *keys: str, default: Any = None) -> Any:
        value: Any = self.data

        for key in keys:
            if not isinstance(value, MutableMapping):
                return default
            value = value.get(key, default)

        return value


    def get_str(self, *keys: str, default: str | None = None) -> str | None:
        value = self.get(*keys, default=default)
        return value if isinstance(value, str) else default