"""
Finds the least-cloudy Sentinel-2 image for an AOI near a target date.

Downloads only the cheap SCL band per candidate date to check its AOI cloud
fraction, nearest-to-target first, and only downloads TCI (producing the
final saved image) for the winning date - never a full band set for a
rejected candidate.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests

from downloader.api import _resolve_credentials
from downloader.clouds import CloudStats, compute_cloud_fraction, find_scl_band
from downloader.downloaders.s2_downloader import Sentinel2
from downloader.geometry.aoi import AOI
from downloader.models import Sentinel2Response, SentinelProduct
from downloader.rasters import find_tci_band
from downloader.tiles import match_tiles
from downloader.visualization import create_aoi_image

DEFAULT_SEARCH_WINDOW_DAYS = 15
DEFAULT_MAX_CLOUD_FRACTION = 0.2


class NoCleanImageFoundError(RuntimeError):
    """Raised when no candidate in the search window
    meets the cloud threshold."""


@dataclass
class BestImageResult:
    """Outcome of `find_best_image`."""

    product: SentinelProduct
    tile_id: str
    cloud_stats: CloudStats
    image_path: Path | None


def _parse_target_date(target_date: str | datetime) -> datetime:
    if isinstance(target_date, datetime):
        return target_date
    return datetime.strptime(target_date, "%Y-%m-%d")


def _fetch_candidates(
    downloader: Sentinel2,
    tile_id: str,
) -> list[SentinelProduct]:
    candidates: list[SentinelProduct] = []
    for start, end in downloader.date_ranges:
        query = downloader.get_query(tile_id, start, end)
        response = requests.get(query, timeout=30)
        response.raise_for_status()
        candidates.extend(Sentinel2Response.from_json(response.json()))
    return candidates


def _product_date(product: SentinelProduct) -> datetime:
    assert product.content_date_start is not None
    return datetime.strptime(product.content_date_start[:10], "%Y-%m-%d")


def find_best_image(
    aoi: AOI,
    target_date: str | datetime,
    *,
    username: str | None = None,
    password: str | None = None,
    search_window_days: int = DEFAULT_SEARCH_WINDOW_DAYS,
    max_cloud_fraction: float = DEFAULT_MAX_CLOUD_FRACTION,
    buffer_meters: float | None = None,
    output_dir: str | Path = "Sentinel-2",
    db_path: str | Path = "data/sentinel.db",
    max_retries: int = 3,
) -> BestImageResult:
    """
    Finds the Sentinel-2 product nearest to `target_date` whose AOI-scoped
    cloud fraction is at or under `max_cloud_fraction`, within
    `search_window_days` on either side, and saves a cropped + boundary
    image of it (TCI_10m) to `output_dir`.

    Raises `ValueError` if no tile intersects `aoi` or no products exist in
    the window at all, or `NoCleanImageFoundError` if products exist but
    none meet the cloud threshold.
    """
    target = _parse_target_date(target_date)

    matches = match_tiles(aoi, db_path=db_path)
    if not matches:
        raise ValueError("No Sentinel-2 tile intersects this AOI")
    tile_id = matches[0].tile_id

    username, password = _resolve_credentials(username, password)

    window_start = target - timedelta(days=search_window_days)
    window_end = target + timedelta(days=search_window_days)

    downloader = Sentinel2(
        username=username,
        password=password,
        tile_ids=[tile_id],
        product_level="L2A",
        db_path=db_path,
        initial_date=window_start.strftime("%Y-%m-%d"),
        last_date=window_end.strftime("%Y-%m-%d"),
        band_selection=["SCL_20m"],
        output_dir=str(output_dir),
        max_retries=max_retries,
    )

    candidates = _fetch_candidates(downloader, tile_id)
    if not candidates:
        raise ValueError(
            f"No Sentinel-2 products found for tile {tile_id} between "
            f"{window_start.date()} and {window_end.date()}"
        )
    candidates.sort(key=lambda product: abs(_product_date(product) - target))

    checked: list[tuple[SentinelProduct, CloudStats]] = []
    winner: SentinelProduct | None = None
    winner_stats: CloudStats | None = None
    for product in candidates:
        status = downloader.download_product(product)
        if status.error:
            continue

        scl_path = find_scl_band(downloader.output_dir / product.name)
        try:
            stats = compute_cloud_fraction(scl_path, aoi, buffer_meters=buffer_meters)
        except ValueError:
            # e.g. this product has no valid (non-NO_DATA) coverage over the
            # AOI at all - a real occurrence for partial/edge-of-swath
            # acquisitions. Skip it like a failed download, try the next.
            continue
        checked.append((product, stats))

        if stats.cloud_fraction <= max_cloud_fraction:
            winner, winner_stats = product, stats
            break

    if winner is None or winner_stats is None:
        if not checked:
            raise ValueError(
                f"None of the {len(candidates)} candidate product(s) for tile {tile_id} "
                "could be checked (download failures and/or no valid AOI coverage)"
            )
        best_product, best_stats = min(checked, key=lambda pair: pair[1].cloud_fraction)
        raise NoCleanImageFoundError(
            f"No image within {search_window_days} days of {target.date()} met the "
            f"{max_cloud_fraction:.0%} cloud threshold (checked {len(checked)}; "
            f"best was {best_product.name} at {best_stats.cloud_fraction:.0%})"
        )

    downloader.band_selection = ["SCL_20m", "TCI_10m"]
    downloader.download_product(winner)

    product_dir = downloader.output_dir / winner.name
    tci_path = find_tci_band(product_dir)
    image_path = create_aoi_image(
        tci_path,
        aoi,
        Path(output_dir) / f"{winner.name}.jpg",
        buffer_meters=buffer_meters,
    )

    return BestImageResult(
        product=winner,
        tile_id=tile_id,
        cloud_stats=winner_stats,
        image_path=image_path,
    )
