"""
Renders a cropped Sentinel image (see `downloader.rasters`) with its AOI's
boundary drawn on top, for visual inspection - saving a JPG like this is the
actual end goal of the geometry-focused TODO items. `ImageOptions` controls
the look (margin `meters`, `filled`, boundary color/width, output format).
"""

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from rasterio.transform import array_bounds

from downloader.geometry.aoi import AOI, GeometryKind
from downloader.geometry.crs import reproject
from downloader.rasters import CroppedImage, crop_window


@dataclass
class ImageOptions:
    """How an AOI image looks and is saved.

    meters: Margin of imagery shown around the geometry's bounding box.
    square: Make the window square (centered on the geometry) before adding `meters`.
    filled: Real imagery everywhere in the window; False blacks out everything
        outside a polygon geometry.
    figsize, edgecolor, linewidth: How the geometry's boundary is drawn.
    extension: Output format, e.g. "jpg" or "png" (used when the output file name is
        generated, as in `downloader.best_image`).
    overwrite: Replace an existing file at the output path.
    dpi: Output resolution.
    """

    meters: float = 125
    square: bool = True
    filled: bool = True
    figsize: tuple[float, float] = (10, 10)
    edgecolor: str = "deepskyblue"
    linewidth: float = 1.5
    extension: str = "jpg"
    overwrite: bool = True
    dpi: int = 150


def _to_display_array(data: np.ndarray) -> np.ndarray:
    bands = data.shape[0]
    if bands == 1:
        return data[0]
    if bands == 3:
        return np.transpose(data, (1, 2, 0))
    raise ValueError(f"Expected a 1-band or 3-band (RGB) image, got {bands} bands")


def render_aoi_image(
    cropped: CroppedImage,
    aoi: AOI,
    *,
    figsize: tuple[float, float] = (10, 10),
    edgecolor: str = "deepskyblue",
    linewidth: float = 1.5,
    cmap: str = "gray",
    title: str | None = None,
) -> tuple[Figure, Axes]:
    """
    Plots `cropped`'s image data with `aoi`'s own geometry drawn on top (a
    polygon's boundary, a line, or a point marker - never a buffered version
    of it), in the cropped image's own CRS. Works for a 1-band (e.g. SCL, shown with
    `cmap`) or 3-band/RGB (e.g. TCI) crop; raises `ValueError` otherwise.
    """
    _, height, width = cropped.data.shape
    left, bottom, right, top = array_bounds(height, width, cropped.transform)
    display_data = _to_display_array(cropped.data)

    fig, ax = plt.subplots(figsize=figsize)
    ax.imshow(display_data, extent=(left, right, bottom, top), cmap=cmap)

    geometry = gpd.GeoSeries([reproject(aoi.geometry, aoi.crs, cropped.crs)], crs=cropped.crs)
    if aoi.kind is GeometryKind.POLYGON:
        geometry.boundary.plot(ax=ax, edgecolor=edgecolor, linewidth=linewidth)
    elif aoi.kind is GeometryKind.LINE:
        geometry.plot(ax=ax, color=edgecolor, linewidth=linewidth)
    else:
        geometry.plot(ax=ax, color=edgecolor, marker="o", markersize=10 * linewidth**2)

    if title:
        ax.set_title(title)
    ax.axis("off")
    fig.tight_layout()

    return fig, ax


def save_figure(
    fig: Figure,
    output_path: str | Path,
    *,
    dpi: int = 150,
    overwrite: bool = True,
) -> Path:
    """Saves `fig` to `output_path` (format from its extension, e.g. `.jpg`) and closes it."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if overwrite or not output_path.exists():
        fig.savefig(output_path, bbox_inches="tight", dpi=dpi)
    plt.close(fig)

    return output_path


def create_aoi_image(
    image_path: str | Path,
    aoi: AOI,
    output_path: str | Path,
    options: ImageOptions | None = None,
    *,
    title: str | None = None,
) -> Path:
    """
    End-to-end: crops `image_path` (e.g. a downloaded TCI_10m band) to a
    window around `aoi` (see `ImageOptions.meters`/`square`/`filled`), draws
    the AOI's boundary on top, and saves it to `output_path` (e.g. a `.jpg`).
    """
    options = options or ImageOptions()
    cropped = crop_window(
        image_path,
        aoi,
        meters=options.meters,
        square=options.square,
        filled=options.filled,
    )
    fig, _ = render_aoi_image(
        cropped,
        aoi,
        figsize=options.figsize,
        edgecolor=options.edgecolor,
        linewidth=options.linewidth,
        title=title,
    )
    return save_figure(fig, output_path, dpi=options.dpi, overwrite=options.overwrite)
