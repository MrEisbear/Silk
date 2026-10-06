import json
from decimal import Decimal
from datetime import datetime, date
from typing import Any
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Declarative Base with JSON serialization and string representation."""

    def to_dict(self) -> dict[str, Any]:
        """Convert model attributes to a plain JSON-serializable dictionary."""
        result: dict[str, Any] = {}
        for column in self.__table__.columns:
            if column.name == "metadata":
                val = getattr(self, "metadata_payload", None)
            else:
                val = getattr(self, column.name)
            if isinstance(val, (datetime, date)):
                result[column.name] = val.isoformat()
            elif isinstance(val, Decimal):
                result[column.name] = float(val)
            else:
                result[column.name] = val
        return result

    def __repr__(self) -> str:
        attrs = ", ".join(f"{k}={v!r}" for k, v in self.to_dict().items() if not k.startswith("_"))
        return f"<{self.__class__.__name__}({attrs})>"
