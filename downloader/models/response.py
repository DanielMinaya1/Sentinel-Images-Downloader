from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from downloader.models.product import SentinelProduct


@dataclass(frozen=True)
class SentinelResponse:
    """Typed wrapper around a Copernicus OData
    `{"value": [...]}` catalogue response."""

    products: list[SentinelProduct] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SentinelResponse":
        products = [SentinelProduct.from_json(item) for item in data.get("value", [])]
        return cls(products=products)

    def __len__(self) -> int:
        return len(self.products)

    def __iter__(self) -> Iterator[SentinelProduct]:
        return iter(self.products)


@dataclass(frozen=True)
class Sentinel1Response(SentinelResponse):
    """Sentinel-1 catalogue response.
    Reserved for Sentinel-1-specific fields."""


@dataclass(frozen=True)
class Sentinel2Response(SentinelResponse):
    """Sentinel-2 catalogue response.
    Reserved for Sentinel-2-specific fields."""
