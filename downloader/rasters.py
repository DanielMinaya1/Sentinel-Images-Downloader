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
import rasterio.features
import rasterio.mask
from pyproj import CRS
from rasterio.transform import Affine
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from downloader.geometry.aoi import AOI, GeometryKind
from downloader.geometry.crs import reproject


def find_band_file(
    product_dir: str | Path,
    band_suffix: str,
    resolution_dir: str,
) -> Path:
    """
    Finds a band file under a downloaded `.SAFE` product directory
    (`GRANULE/*/IMG_DATA/<resolution_dir>/*_<band_suffix>.jp2`, the layout
    this project's own downloader produces), so a caller can pass a product
    folder instead of knowing SAFE's internal structure.
    """
    product_dir = Path(product_dir)
    matches = sorted(product_dir.glob(f"GRANULE/*/IMG_DATA/{resolution_dir}/*_{band_suffix}.jp2"))
    if not matches:
        raise FileNotFoundError(f"No {band_suffix} band found under {product_dir}")
    return matches[0]


def find_tci_band(product_dir: str | Path) -> Path:
    """Finds the TCI_10m (true color) band under a downloaded `.SAFE` product directory."""
    return find_band_file(product_dir, "TCI_10m", "R10m")


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


def _write_geotiff(data: np.ndarray, profile: dict, output_path: str | Path | None) -> Path | None:
    """Writes `data` as a GeoTIFF (creating parent dirs), or does nothing if no path is given."""
    if output_path is None:
        return None
    written_path = Path(output_path)
    written_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(written_path, "w", **{**profile, "driver": "GTiff"}) as dst:
        dst.write(data)
    return written_path


def crop_image(
    image_path: str | Path,
    aoi: AOI,
    buffer_meters: float | None = None,
    output_path: str | Path | None = None,
) -> CroppedImage:
    """
    Crops `image_path` (e.g. a downloaded TCI_10m band) to `aoi`'s
    (buffered) polygon, optionally writing the result to `output_path`.
    Pixels outside that polygon are zeroed; see `crop_window` for a
    rectangular crop with real imagery everywhere.

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

    return CroppedImage(
        data=clipped,
        transform=profile["transform"],
        crs=profile["crs"],
        output_path=_write_geotiff(clipped, profile, output_path),
    )


def _window_geometry(
    geometry: BaseGeometry,
    meters: float,
    square: bool,
) -> BaseGeometry:
    """`geometry`'s bounding box grown by `meters` on every side, optionally made square."""
    minx, miny, maxx, maxy = geometry.bounds
    if square:
        center_x, center_y = (minx + maxx) / 2, (miny + maxy) / 2
        half_side = max(maxx - minx, maxy - miny) / 2 + meters
        return box(
            center_x - half_side, center_y - half_side, center_x + half_side, center_y + half_side
        )
    return box(minx - meters, miny - meters, maxx + meters, maxy + meters)


def crop_window(
    image_path: str | Path,
    aoi: AOI,
    *,
    meters: float = 0.0,
    square: bool = True,
    filled: bool = True,
    output_path: str | Path | None = None,
) -> CroppedImage:
    """
    Crops `image_path` to a rectangular window around `aoi`: its bounding
    box grown by `meters` on every side (so the surroundings are visible),
    made square by default. Meant for viewing - unlike `crop_image`, every
    pixel in the window is real imagery.

    With `filled=False`, pixels outside a polygon AOI are zeroed (blacked
    out) instead, leaving only the imagery inside the polygon; that has no
    effect on a point or line AOI, which has no interior to keep.

    The window is measured in the raster's own CRS, so it must be a
    projected (metric) one, as Sentinel-2 bands are. Raises whatever
    `rasterio.mask.mask` raises if the window doesn't overlap the raster.
    """
    with rasterio.open(image_path) as dataset:
        if not dataset.crs.is_projected:
            raise ValueError(f"{image_path} is not in a projected (metric) CRS")
        geometry = reproject(aoi.geometry, aoi.crs, dataset.crs)
        window = _window_geometry(geometry, meters, square)
        # all_touched keeps the window's edge pixels instead of blanking them.
        clipped, transform = rasterio.mask.mask(dataset, [window], crop=True, all_touched=True)
        profile = dataset.profile.copy()

    profile.update(height=clipped.shape[1], width=clipped.shape[2], transform=transform)

    if not filled and aoi.kind is GeometryKind.POLYGON:
        inside = rasterio.features.geometry_mask(
            [geometry], out_shape=clipped.shape[1:], transform=transform, invert=True
        )
        clipped = np.where(inside, clipped, 0).astype(clipped.dtype)

    return CroppedImage(
        data=clipped,
        transform=transform,
        crs=profile["crs"],
        output_path=_write_geotiff(clipped, profile, output_path),
    )
