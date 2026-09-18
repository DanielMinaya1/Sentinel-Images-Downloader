"""
Local raster clipping/cropping shared by every feature that needs "just the
pixels under this AOI" from an already-downloaded Sentinel image -
`downloader.clouds` (statistics) and `crop_image` below (an actual output
file) both build on the same `clip_raster` primitive.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
import rasterio.mask
from pyproj import CRS
from rasterio.transform import Affine

from downloader.geometry.aoi import AOI


def clip_raster(
    image_path: str | Path,
    aoi: AOI,
    buffer_meters: float | None = None,
) -> tuple[np.ndarray, dict]:
    """
    Opens `image_path` and clips it to `aoi`'s (buffered) polygon.

    Returns the clipped pixel array and a rasterio profile describing it
    (the original dataset's profile, with `height`/`width`/`transform`
    updated to reflect the crop). Raises whatever `rasterio.mask.mask`
    raises if the AOI doesn't overlap the raster at all.
    """
    with rasterio.open(image_path) as dataset:
        polygon = aoi.to_polygon(buffer_meters=buffer_meters, crs=dataset.crs)
        clipped, transform = rasterio.mask.mask(dataset, [polygon], crop=True)
        profile = dataset.profile.copy()

    profile.update(
        height=clipped.shape[1],
        width=clipped.shape[2],
        transform=transform,
    )
    return clipped, profile


@dataclass
class CroppedImage:
    """Outcome of `crop_image`."""

    data: np.ndarray
    transform: Affine
    crs: CRS
    output_path: Path | None


def crop_image(
    image_path: str | Path,
    aoi: AOI,
    buffer_meters: float | None = None,
    output_path: str | Path | None = None,
) -> CroppedImage:
    """
    Crops `image_path` (e.g. a downloaded TCI_10m band) to `aoi`'s
    (buffered) polygon, optionally writing the result to `output_path`.

    The output is always written as GeoTIFF regardless of the input's
    format - Sentinel-2 bands are JP2, and JP2 *write* support isn't
    reliably available across GDAL builds the way JP2 *read* is, whereas
    GeoTIFF write is universal. `output_path` should be a `.tif` path.
    """
    clipped, profile = clip_raster(
        image_path,
        aoi,
        buffer_meters=buffer_meters,
    )

    written_path = None
    if output_path is not None:
        written_path = Path(output_path)
        written_path.parent.mkdir(parents=True, exist_ok=True)
        output_profile = {**profile, "driver": "GTiff"}
        with rasterio.open(written_path, "w", **output_profile) as dst:
            dst.write(clipped)

    return CroppedImage(
        data=clipped,
        transform=profile["transform"],
        crs=profile["crs"],
        output_path=written_path,
    )
