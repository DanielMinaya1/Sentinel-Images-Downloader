"""
Renders a cropped Sentinel image (see `downloader.rasters`) with its AOI's
boundary drawn on top, for visual inspection - saving a JPG like this is the
actual end goal of the geometry-focused TODO items.
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from rasterio.transform import array_bounds

from downloader.geometry.aoi import AOI
from downloader.rasters import CroppedImage, crop_image


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
    buffer_meters: float | None = None,
    *,
    figsize: tuple[float, float] = (10, 10),
    edgecolor: str = "deepskyblue",
    linewidth: float = 1.5,
    cmap: str = "gray",
    title: str | None = None,
) -> tuple[Figure, Axes]:
    """
    Plots `cropped`'s image data with `aoi`'s boundary drawn on top, in the
    cropped image's own CRS. Works for a 1-band (e.g. SCL, shown with
    `cmap`) or 3-band/RGB (e.g. TCI) crop; raises `ValueError` otherwise.
    """
    _, height, width = cropped.data.shape
    left, bottom, right, top = array_bounds(height, width, cropped.transform)
    display_data = _to_display_array(cropped.data)

    fig, ax = plt.subplots(figsize=figsize)
    ax.imshow(display_data, extent=(left, right, bottom, top), cmap=cmap)

    boundary = aoi.to_polygon(buffer_meters=buffer_meters, crs=cropped.crs)
    gpd.GeoSeries([boundary], crs=cropped.crs).boundary.plot(
        ax=ax, edgecolor=edgecolor, linewidth=linewidth
    )

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
    buffer_meters: float | None = None,
    **render_kwargs,
) -> Path:
    """
    End-to-end: crops `image_path` (e.g. a downloaded TCI_10m band) to
    `aoi`, renders it with the AOI's boundary overlaid, and saves it to
    `output_path` (e.g. a `.jpg`).
    """
    cropped = crop_image(image_path, aoi, buffer_meters=buffer_meters)
    fig, _ = render_aoi_image(cropped, aoi, buffer_meters=buffer_meters, **render_kwargs)
    return save_figure(fig, output_path)
