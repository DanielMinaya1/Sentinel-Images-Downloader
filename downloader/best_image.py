"""
Finds the least-cloudy Sentinel-2 image for an AOI, either near a target
date (`find_best_image`) or anywhere in a date range
(`find_best_image_in_range`).

Downloads only the cheap SCL band per candidate date to check its AOI cloud
fraction, and only downloads TCI (producing the final saved image) for the
winning date - never a full band set for a rejected candidate.
"""

import contextlib
import logging
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import requests

from downloader.api import _resolve_credentials
from downloader.clouds import CloudStats, compute_cloud_fraction, find_scl_band
from downloader.downloaders.s2_downloader import Sentinel2
from downloader.geometry.aoi import AOI
from downloader.models import DownloadStatus, Sentinel2Response, SentinelProduct
from downloader.rasters import find_tci_band
from downloader.tiles import match_tiles
from downloader.visualization import ImageOptions, create_aoi_image

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_WINDOW_DAYS = 15
DEFAULT_MAX_CLOUD_FRACTION = 0.2
DEFAULT_RANGE_MAX_CLOUD_FRACTION = 0.05


class NoCleanImageFoundError(RuntimeError):
    """Raised when no candidate in the search window
    meets the cloud threshold."""


@dataclass
class BestImageResult:
    """Outcome of `find_best_image` / `find_best_image_in_range`."""

    product: SentinelProduct
    tile_id: str
    cloud_stats: CloudStats
    image_path: Path | None


def _parse_date(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, "%Y-%m-%d")


def _as_aoi(geometry: AOI | dict[str, Any]) -> AOI:
    """Accepts an `AOI`, or a GeoJSON geometry/Feature dict (assumed EPSG:4326)."""
    return geometry if isinstance(geometry, AOI) else AOI.from_geojson(geometry)


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


def _evaluate_candidate(
    downloader: Sentinel2,
    product: SentinelProduct,
    aoi: AOI,
    buffer_meters: float | None,
) -> CloudStats | None:
    """
    Downloads `product`'s SCL band and returns its AOI cloud stats, or None
    if this candidate can't be used - a failed download, or no valid
    (non-NO_DATA) coverage over the AOI, which is a real occurrence for
    partial/edge-of-swath acquisitions. Either way the search moves on to
    the next candidate instead of failing outright.
    """
    status = downloader.download_product(product)
    if status.status == DownloadStatus.FAILED:
        logger.warning(f"Skipping {product.name}: SCL download failed")
        return None

    try:
        scl_path = find_scl_band(downloader.output_dir / product.name)
        return compute_cloud_fraction(scl_path, aoi, buffer_meters=buffer_meters)
    except (FileNotFoundError, ValueError) as e:
        logger.warning(f"Skipping {product.name}: {e}")
        return None


def _render_winner(
    downloader: Sentinel2,
    winner: SentinelProduct,
    aoi: AOI,
    output_dir: str | Path,
    options: ImageOptions,
) -> Path:
    """Downloads the winner's TCI band (SCL is already local) and saves its AOI image."""
    downloader.band_selection = ["SCL_20m", "TCI_10m"]
    status = downloader.download_product(winner)
    if status.status == DownloadStatus.FAILED:
        detail = status.error or "; ".join(
            f"{f.file_path.name}: {f.error}" for f in status.files if f.error
        )
        raise RuntimeError(f"Failed to download TCI_10m for {winner.name}: {detail}")

    tci_path = find_tci_band(downloader.output_dir / winner.name)
    image_path = Path(output_dir) / f"{winner.name}.{options.extension}"
    return create_aoi_image(tci_path, aoi, image_path, options)


def find_best_image(
    aoi: AOI,
    target_date: str | datetime,
    *,
    username: str | None = None,
    password: str | None = None,
    search_window_days: int = DEFAULT_SEARCH_WINDOW_DAYS,
    max_cloud_fraction: float = DEFAULT_MAX_CLOUD_FRACTION,
    buffer_meters: float | None = None,
    image_options: ImageOptions | None = None,
    output_dir: str | Path = "Sentinel-2",
    db_path: str | Path = "data/sentinel.db",
    max_retries: int = 3,
) -> BestImageResult:
    """
    Finds the Sentinel-2 product nearest to `target_date` whose AOI-scoped
    cloud fraction is at or under `max_cloud_fraction`, within
    `search_window_days` on either side, and saves a cropped + boundary
    image of it (TCI_10m) to `output_dir`. `buffer_meters` only affects the
    cloud check (needed for a point/line); `image_options` controls the image.

    Raises `ValueError` if no tile intersects `aoi` or no products exist in
    the window at all, or `NoCleanImageFoundError` if products exist but
    none meet the cloud threshold. See `find_best_image_in_range` for a
    date-range version that returns None instead of raising.
    """
    target = _parse_date(target_date)

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
        stats = _evaluate_candidate(downloader, product, aoi, buffer_meters)
        if stats is None:
            continue
        checked.append((product, stats))

        if stats.unusable_fraction <= max_cloud_fraction:
            winner, winner_stats = product, stats
            break

    if winner is None or winner_stats is None:
        if not checked:
            raise ValueError(
                f"None of the {len(candidates)} candidate product(s) for tile {tile_id} "
                "could be checked (download failures and/or no valid AOI coverage)"
            )
        best_product, best_stats = min(checked, key=lambda pair: pair[1].unusable_fraction)
        raise NoCleanImageFoundError(
            f"No image within {search_window_days} days of {target.date()} met the "
            f"{max_cloud_fraction:.0%} cloud threshold (checked {len(checked)}; "
            f"best was {best_product.name} at {best_stats.unusable_fraction:.0%})"
        )

    image_path = _render_winner(
        downloader, winner, aoi, output_dir, image_options or ImageOptions()
    )

    return BestImageResult(
        product=winner,
        tile_id=tile_id,
        cloud_stats=winner_stats,
        image_path=image_path,
    )


def find_best_image_in_range(
    geometry: AOI | dict[str, Any],
    start_date: str | datetime,
    end_date: str | datetime,
    output_dir: str | Path,
    *,
    username: str | None = None,
    password: str | None = None,
    max_cloud_fraction: float = DEFAULT_RANGE_MAX_CLOUD_FRACTION,
    prefer: Literal["recent", "clearest"] = "recent",
    buffer_meters: float | None = None,
    image_options: ImageOptions | None = None,
    download_dir: str | Path | None = None,
    db_path: str | Path = "data/sentinel.db",
    max_retries: int = 3,
) -> BestImageResult | None:
    """
    Finds a Sentinel-2 image over `geometry` between `start_date` and
    `end_date` (inclusive) and saves a cropped image of it, with the
    geometry's boundary drawn on top, to `output_dir` as a JPG.

    A date qualifies if its AOI-scoped cloud fraction is at or under
    `max_cloud_fraction` (5% by default; 0.0 means no clouds at all).
    NO_DATA pixels (a partial acquisition cutting through the geometry)
    count against a date the same way clouds do. Which
    qualifying date wins depends on `prefer`:

    - "recent" (default): the most recent qualifying date. Searches
      newest-first and stops at the first one that qualifies, so it only
      downloads the small SCL band for as many dates as it takes.
    - "clearest": the lowest cloud fraction across every usable date in the
      range (ties go to the most recent), stopping early only on a perfectly
      clear (0%) one since nothing can beat it. Checks more dates.

    Returns None if no date qualifies, or the range has no usable products.

    Args:
        geometry: An `AOI`, or a GeoJSON geometry/Feature dict (EPSG:4326).
        start_date, end_date: "YYYY-MM-DD" strings or datetimes, inclusive.
        output_dir: Where the final JPG is saved.
        download_dir: Where raw Sentinel-2 product data is downloaded. By
            default a temporary directory that's deleted afterwards, so
            only the JPG is left behind; pass a path to keep the raw data
            (and reuse it across calls).
        buffer_meters: Area used for the *cloud check* only. Required for a
            point/line geometry (no area of its own); a polygon is checked
            as-is unless you pad it here.
        image_options: How the saved image looks: the `meters` of imagery
            shown around the geometry, `filled`, boundary style, output
            format... (see `ImageOptions`). Defaults to a square window with
            125 m of margin, saved as JPG.

    Raises `ValueError` for an invalid range or a geometry no Sentinel-2
    tile intersects.
    """
    if prefer not in ("recent", "clearest"):
        raise ValueError(f"prefer must be 'recent' or 'clearest', got {prefer!r}")

    aoi = _as_aoi(geometry)
    start, end = _parse_date(start_date), _parse_date(end_date)
    if start > end:
        raise ValueError(
            f"start_date ({start.date()}) must be on or before end_date ({end.date()})"
        )

    matches = match_tiles(aoi, db_path=db_path)
    if not matches:
        raise ValueError("No Sentinel-2 tile intersects this geometry")
    tile_id = matches[0].tile_id

    username, password = _resolve_credentials(username, password)

    with contextlib.ExitStack() as stack:
        if download_dir is None:
            work_dir = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        else:
            work_dir = Path(download_dir)

        downloader = Sentinel2(
            username=username,
            password=password,
            tile_ids=[tile_id],
            product_level="L2A",
            db_path=db_path,
            initial_date=start.strftime("%Y-%m-%d"),
            last_date=end.strftime("%Y-%m-%d"),
            band_selection=["SCL_20m"],
            output_dir=str(work_dir),
            max_retries=max_retries,
        )

        candidates = _fetch_candidates(downloader, tile_id)
        logger.info(f"Found {len(candidates)} candidate product(s) for tile {tile_id}")
        # Most recent first, so a tie on cloud fraction goes to the newer one.
        candidates.sort(key=_product_date, reverse=True)

        best: tuple[SentinelProduct, CloudStats] | None = None
        for product in candidates:
            stats = _evaluate_candidate(downloader, product, aoi, buffer_meters)
            if stats is None:
                continue
            logger.info(f"{product.name}: {stats.unusable_fraction:.1%} cloud/no-data over the AOI")

            if prefer == "recent":
                if stats.unusable_fraction <= max_cloud_fraction:
                    best = (product, stats)
                    break
                continue

            if best is None or stats.unusable_fraction < best[1].unusable_fraction:
                best = (product, stats)
            if stats.unusable_fraction == 0.0:
                break

        if best is None or best[1].unusable_fraction > max_cloud_fraction:
            return None

        winner, winner_stats = best
        image_path = _render_winner(
            downloader, winner, aoi, output_dir, image_options or ImageOptions()
        )

    return BestImageResult(
        product=winner,
        tile_id=tile_id,
        cloud_stats=winner_stats,
        image_path=image_path,
    )
