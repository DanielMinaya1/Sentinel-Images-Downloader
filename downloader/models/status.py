from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


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
    error: Optional[str] = None


@dataclass
class SentinelDownloadStatus:
    """Outcome of downloading one SAFE product 
    (manifest + its filtered files)."""

    product_id: str
    product_name: str
    files: List[FileDownloadResult] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def status(self) -> DownloadStatus:
        if self.error is not None or self.failed > 0:
            return DownloadStatus.FAILED
        if not self.files:
            return DownloadStatus.SKIPPED
        return DownloadStatus.SUCCESS

    @property
    def succeeded(self) -> int:
        return sum(
            1 
            for f in self.files 
            if f.status == DownloadStatus.SUCCESS
        )

    @property
    def failed(self) -> int:
        return sum(
            1 
            for f in self.files 
            if f.status == DownloadStatus.FAILED
        )

    @property
    def skipped(self) -> int:
        return sum(
            1 
            for f in self.files 
            if f.status == DownloadStatus.SKIPPED
        )


@dataclass
class Sentinel1DownloadStatus(SentinelDownloadStatus):
    orbit_direction: Optional[str] = None
    polarization_mode: Optional[List[str]] = None


@dataclass
class Sentinel2DownloadStatus(SentinelDownloadStatus):
    product_level: Optional[str] = None
    band_selection: Optional[List[str]] = None


@dataclass
class TileDownloadSummary:
    """Outcome of downloading every product found for one tile, 
    across all date ranges."""

    tile_id: str
    products: List[SentinelDownloadStatus] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        return sum(p.succeeded for p in self.products)

    @property
    def failed(self) -> int:
        return sum(p.failed for p in self.products)

    @property
    def skipped(self) -> int:
        return sum(p.skipped for p in self.products)
