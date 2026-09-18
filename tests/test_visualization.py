import matplotlib

matplotlib.use("Agg")  # headless backend, no display needed for tests

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from downloader.geometry import AOI
from downloader.rasters import crop_image
from downloader.visualization import create_aoi_image, render_aoi_image, save_figure

CRS = "EPSG:32718"
_TRANSFORM = from_origin(300000, 6000000, 10, 10)


def write_raster(path, band_count):
    data = np.zeros((band_count, 4, 4), dtype=np.uint8)
    for band in range(band_count):
        data[band] = np.arange(16).reshape(4, 4) + band
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=band_count,
        dtype=np.uint8,
        crs=CRS,
        transform=_TRANSFORM,
    ) as dst:
        dst.write(data)
    return path


@pytest.fixture
def rgb_path(tmp_path):
    return write_raster(tmp_path / "tci.tif", 3)


@pytest.fixture
def single_band_path(tmp_path):
    return write_raster(tmp_path / "scl.tif", 1)


@pytest.fixture
def two_band_path(tmp_path):
    return write_raster(tmp_path / "unsupported.tif", 2)


def whole_raster_aoi():
    return AOI.from_shapely(box(300000, 5999960, 300040, 6000000), crs=CRS)


class TestRenderAoiImage:
    def test_renders_rgb_crop_with_boundary_and_title(self, rgb_path):
        cropped = crop_image(rgb_path, whole_raster_aoi())

        fig, ax = render_aoi_image(cropped, whole_raster_aoi(), title="my AOI")

        assert len(ax.images) == 1
        assert len(ax.collections) == 1  # the plotted boundary
        assert ax.get_title() == "my AOI"

    def test_renders_single_band_crop(self, single_band_path):
        cropped = crop_image(single_band_path, whole_raster_aoi())

        fig, ax = render_aoi_image(cropped, whole_raster_aoi())

        assert len(ax.images) == 1

    def test_unsupported_band_count_raises(self, two_band_path):
        cropped = crop_image(two_band_path, whole_raster_aoi())

        with pytest.raises(ValueError, match="1-band or 3-band"):
            render_aoi_image(cropped, whole_raster_aoi())


class TestSaveFigure:
    def test_writes_a_nonempty_jpg(self, tmp_path, rgb_path):
        cropped = crop_image(rgb_path, whole_raster_aoi())
        fig, _ = render_aoi_image(cropped, whole_raster_aoi())
        output_path = tmp_path / "out.jpg"

        result = save_figure(fig, output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_overwrite_false_leaves_existing_file_untouched(self, tmp_path, rgb_path):
        output_path = tmp_path / "out.jpg"
        output_path.write_bytes(b"already here")

        cropped = crop_image(rgb_path, whole_raster_aoi())
        fig, _ = render_aoi_image(cropped, whole_raster_aoi())
        save_figure(fig, output_path, overwrite=False)

        assert output_path.read_bytes() == b"already here"

    def test_creates_missing_output_parent_directories(self, tmp_path, rgb_path):
        cropped = crop_image(rgb_path, whole_raster_aoi())
        fig, _ = render_aoi_image(cropped, whole_raster_aoi())
        output_path = tmp_path / "nested" / "dir" / "out.jpg"

        save_figure(fig, output_path)

        assert output_path.exists()


class TestCreateAoiImage:
    def test_end_to_end_produces_a_jpg(self, tmp_path, rgb_path):
        output_path = tmp_path / "aoi.jpg"

        result = create_aoi_image(rgb_path, whole_raster_aoi(), output_path)

        assert result == output_path
        assert output_path.exists()
        assert output_path.stat().st_size > 0
