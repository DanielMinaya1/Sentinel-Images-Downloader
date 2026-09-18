"""
AOI-scoped cloud statistics from a downloaded Sentinel-2 SCL (Scene
Classification) band - unlike Copernicus's tile-wide cloud-cover filter,
this reads the actual pixels under (and, for a point/line, around) an AOI.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from downloader.geometry.aoi import AOI
from downloader.rasters import clip_raster, find_band_file

# Sentinel-2 L2A Scene Classification classes considered "cloud" for
# filtering purposes: cloud shadows, cloud (medium/high probability), and
# thin cirrus. Class 0 (NO_DATA) is always excluded separately, regardless
# of this set.
DEFAULT_CLOUD_SCL_CLASSES: frozenset[int] = frozenset({3, 8, 9, 10})

_NO_DATA_SCL_CLASS = 0


@dataclass
class CloudStats:
    """Outcome of `compute_cloud_fraction`."""

    cloud_fraction: float
    cloud_pixels: int
    valid_pixels: int
    total_pixels: int


def find_scl_band(product_dir: str | Path) -> Path:
    """Finds the SCL_20m band under a downloaded `.SAFE` product directory."""
    return find_band_file(product_dir, "SCL_20m", "R20m")


def compute_cloud_fraction(
    scl_path: str | Path,
    aoi: AOI,
    buffer_meters: float | None = None,
    cloud_classes: frozenset[int] = DEFAULT_CLOUD_SCL_CLASSES,
) -> CloudStats:
    """
    Computes the fraction of cloud-classified pixels within `aoi` (buffered
    by `buffer_meters` for a POINT/LINE-kind AOI, which has no area of its
    own - see `AOI.to_polygon`) from a local SCL raster.

    Raises `ValueError` if the AOI has no valid (non-NO_DATA) coverage in
    this raster at all - e.g. it falls entirely outside the tile.

    Note: SCL is 20m resolution. A `buffer_meters` much smaller than that
    (e.g. a few meters) can clip a window covering only a sliver of a
    pixel, or even miss every pixel center and raise the error above -
    check `CloudStats.valid_pixels` if the result covers only one or two
    pixels and you want to be sure it's statistically meaningful.
    """
    clipped, _ = clip_raster(scl_path, aoi, buffer_meters=buffer_meters)

    values = clipped[0]
    # SCL class 0 means NO_DATA in the classification itself, so treat it as
    # invalid regardless of the file's own nodata tag - JP2 doesn't reliably
    # carry one.
    valid_mask = values != _NO_DATA_SCL_CLASS
    valid_pixels = int(valid_mask.sum())
    if valid_pixels == 0:
        raise ValueError("AOI has no valid pixel coverage in this raster")

    cloud_mask = valid_mask & np.isin(values, list(cloud_classes))
    cloud_pixels = int(cloud_mask.sum())

    return CloudStats(
        cloud_fraction=cloud_pixels / valid_pixels,
        cloud_pixels=cloud_pixels,
        valid_pixels=valid_pixels,
        total_pixels=int(values.size),
    )
