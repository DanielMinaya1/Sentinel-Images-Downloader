"""
Discovers Sentinel-2 tiles touching an AOI's bounding box via the
Copernicus catalogue, used to seed `data/sentinel.db`'s tile-footprint
cache (see `downloader.tiles.matcher`).
"""

import re

import requests
from pyproj import CRS
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

from downloader.config.endpoints import DATA_URL
from downloader.config.templates import S2_TILE_DISCOVERY_QUERY
from downloader.geometry.crs import reproject

WGS84 = CRS.from_epsg(4326)

# A POINT-kind (or axis-aligned LINE-kind) AOI's envelope degenerates to a
# Point/LineString with zero area, which has no `.exterior` to build a query
# ring from. Pad it by a small margin (well under a single ~110km S2 tile)
# so there's always a real quadrilateral to search with.
_MIN_BBOX_MARGIN_DEGREES = 0.01

_TILE_ID_PATTERN = re.compile(r"_(T\d{2}[A-Z]{3})_")


def _extract_tile_id(product_name: str) -> str | None:
    match = _TILE_ID_PATTERN.search(product_name)
    return match.group(1) if match else None


def discover_candidate_tiles(bbox: BaseGeometry, crs: CRS) -> dict[str, BaseGeometry]:
    """
    Queries the Copernicus catalogue for Sentinel-2 products touching `bbox`
    and returns every distinct tile id seen, mapped to its real footprint
    (both in EPSG:4326, as returned by the API) - this is how tiles on both
    sides of a boundary get discovered from one query, not just whichever
    tile happened to own the first result.
    """
    if crs != WGS84:
        bbox = reproject(bbox, crs, WGS84)

    minx, miny, maxx, maxy = bbox.bounds
    if maxx - minx < _MIN_BBOX_MARGIN_DEGREES:
        minx -= _MIN_BBOX_MARGIN_DEGREES
        maxx += _MIN_BBOX_MARGIN_DEGREES
    if maxy - miny < _MIN_BBOX_MARGIN_DEGREES:
        miny -= _MIN_BBOX_MARGIN_DEGREES
        maxy += _MIN_BBOX_MARGIN_DEGREES
    bbox = box(minx, miny, maxx, maxy)

    ring = ", ".join(f"{x} {y}" for x, y in bbox.exterior.coords)
    query = S2_TILE_DISCOVERY_QUERY.format(data_url=DATA_URL, bbox_ring=ring)

    response = requests.get(query, timeout=30)
    response.raise_for_status()

    tiles: dict[str, BaseGeometry] = {}
    for product in response.json().get("value", []):
        tile_id = _extract_tile_id(product.get("Name", ""))
        if tile_id and tile_id not in tiles and "GeoFootprint" in product:
            tiles[tile_id] = shape(product["GeoFootprint"])

    return tiles
