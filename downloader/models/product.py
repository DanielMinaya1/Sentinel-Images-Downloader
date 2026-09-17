from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SentinelProduct:
    """A single product entry from the 
    Copernicus OData catalogue response."""

    id: str
    name: str
    content_date_start: str | None = None
    content_date_end: str | None = None
    online: bool | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SentinelProduct":
        content_date = data.get("ContentDate") or {}
        return cls(
            id=data["Id"],
            name=data["Name"],
            content_date_start=content_date.get("Start"),
            content_date_end=content_date.get("End"),
            online=data.get("Online"),
        )
