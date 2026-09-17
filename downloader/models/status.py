from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DownloadStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class FileDownloadResult:
    """Outcome of downloading a single file within a product."""

    file_path: Path
    status: DownloadStatus
    attempts: int = 0
    error: str | None = None


@dataclass
class SentinelDownloadStatus:
    """Outcome of downloading one SAFE product
    (manifest + its filtered files)."""

    product_id: str
    product_name: str
    files: list[FileDownloadResult] = field(default_factory=list)
    error: str | None = None

    @property
    def status(self) -> DownloadStatus:
        if self.error is not None or self.failed > 0:
            return DownloadStatus.FAILED
        if not self.files:
            return DownloadStatus.SKIPPED
        return DownloadStatus.SUCCESS

    @property
    def succeeded(self) -> int:
        return sum(1 for f in self.files if f.status == DownloadStatus.SUCCESS)

    @property
    def failed(self) -> int:
        return sum(1 for f in self.files if f.status == DownloadStatus.FAILED)

    @property
    def skipped(self) -> int:
        return sum(1 for f in self.files if f.status == DownloadStatus.SKIPPED)


@dataclass
class Sentinel1DownloadStatus(SentinelDownloadStatus):
    orbit_direction: str | None = None
    polarization_mode: list[str] | None = None


@dataclass
class Sentinel2DownloadStatus(SentinelDownloadStatus):
    product_level: str | None = None
    band_selection: list[str] | None = None


@dataclass
class TileDownloadSummary:
    """Outcome of downloading every product found for one tile,
    across all date ranges."""

    tile_id: str
    products: list[SentinelDownloadStatus] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(p.succeeded for p in self.products)

    @property
    def failed(self) -> int:
        return sum(p.failed for p in self.products)

    @property
    def skipped(self) -> int:
        return sum(p.skipped for p in self.products)


@dataclass
class RunSummary:
    """Outcome of a full `download()` run, across every tile in the config."""

    tiles: list[TileDownloadSummary] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(t.succeeded for t in self.tiles)

    @property
    def failed(self) -> int:
        return sum(t.failed for t in self.tiles)

    @property
    def skipped(self) -> int:
        return sum(t.skipped for t in self.tiles)
