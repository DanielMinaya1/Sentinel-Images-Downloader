"""
Matches an AOI against known Sentinel-2 tiles, backed by the
`s2_tile_footprints` cache in `data/sentinel.db` and falling back to
`downloader.tiles.discovery` on a cache miss.
"""

from dataclasses import dataclass
from pathlib import Path

from shapely.geometry.base import BaseGeometry

from downloader.geometry.aoi import AOI, GeometryKind
from downloader.geometry.crs import estimate_metric_crs, reproject
from downloader.storage.repositories import TileFootprintRepository
from downloader.tiles.discovery import WGS84, discover_candidate_tiles

DEFAULT_DB_PATH = "data/sentinel.db"


@dataclass
class TileMatch:
    """A Sentinel-2 tile intersecting an AOI, and how well it covers it."""

    tile_id: str
    footprint: BaseGeometry
    overlap_fraction: float
    contains: bool


def _overlap_fraction(
    aoi_geometry: BaseGeometry,
    tile_footprint: BaseGeometry,
    kind: GeometryKind,
) -> float:
    intersection = aoi_geometry.intersection(tile_footprint)
    if kind is GeometryKind.POLYGON:
        return intersection.area / aoi_geometry.area if aoi_geometry.area else 0.0
    if kind is GeometryKind.LINE:
        return intersection.length / aoi_geometry.length if aoi_geometry.length else 0.0
    return 1.0 if not intersection.is_empty else 0.0


def match_tiles(aoi: AOI, db_path: str | Path = DEFAULT_DB_PATH) -> list[TileMatch]:
    """
    Returns every Sentinel-2 tile intersecting `aoi`, sorted best-first
    (highest overlap first; empty list if none intersect).

    Checks the `s2_tile_footprints` cache first; only queries the
    Copernicus catalogue on a cache miss, caching whatever it discovers
    for next time.
    """
    repository = TileFootprintRepository(db_path)
    try:
        candidates = {
            tile_id: footprint
            for tile_id, footprint in repository.all().items()
            if footprint.intersects(aoi.geometry)
        }

        if not candidates:
            discovered = discover_candidate_tiles(aoi.geometry.envelope, aoi.crs)
            for tile_id, footprint in discovered.items():
                repository.upsert(tile_id, footprint)
            candidates = {
                tile_id: footprint
                for tile_id, footprint in discovered.items()
                if footprint.intersects(aoi.geometry)
            }
    finally:
        repository.close()

    if not candidates:
        return []

    metric_crs = estimate_metric_crs(aoi.geometry, aoi.crs)
    aoi_metric = reproject(aoi.geometry, aoi.crs, metric_crs)

    matches = []
    for tile_id, footprint in candidates.items():
        footprint_metric = reproject(footprint, WGS84, metric_crs)
        matches.append(
            TileMatch(
                tile_id=tile_id,
                footprint=footprint,
                overlap_fraction=_overlap_fraction(aoi_metric, footprint_metric, aoi.kind),
                contains=footprint_metric.contains(aoi_metric),
            )
        )

    matches.sort(key=lambda match: match.overlap_fraction, reverse=True)
    return matches
