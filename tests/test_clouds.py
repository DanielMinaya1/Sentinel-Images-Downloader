import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from downloader.clouds import compute_cloud_fraction, find_scl_band
from downloader.geometry import AOI

CRS = "EPSG:32718"  # UTM zone 18S, matches the project's Chile-based test data.

# A 4x4, 20m-pixel raster: top two rows clear (class 4), bottom two rows
# cloudy (class 9). Origin (300000, 6000000), so pixel centers land at
# y = 5999990/5999970 (clear rows) and y = 5999950/5999930 (cloudy rows).
_TRANSFORM = from_origin(300000, 6000000, 20, 20)
_SCL_DATA = np.array(
    [
        [4, 4, 4, 4],
        [4, 4, 4, 4],
        [9, 9, 9, 9],
        [9, 9, 9, 9],
    ],
    dtype=np.uint8,
)


@pytest.fixture
def scl_path(tmp_path):
    path = tmp_path / "T18HXE_20230115T143751_SCL_20m.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype=np.uint8,
        crs=CRS,
        transform=_TRANSFORM,
    ) as dst:
        dst.write(_SCL_DATA, 1)
    return path


def polygon_aoi(*bounds):
    return AOI.from_shapely(box(*bounds), crs=CRS)


class TestComputeCloudFraction:
    def test_clear_half_is_cloud_free(self, scl_path):
        aoi = polygon_aoi(300005, 5999965, 300075, 5999995)

        stats = compute_cloud_fraction(scl_path, aoi)

        assert stats.cloud_fraction == 0.0
        assert stats.cloud_pixels == 0
        assert stats.valid_pixels == 8

    def test_cloudy_half_is_fully_cloud(self, scl_path):
        aoi = polygon_aoi(300005, 5999925, 300075, 5999955)

        stats = compute_cloud_fraction(scl_path, aoi)

        assert stats.cloud_fraction == 1.0
        assert stats.cloud_pixels == stats.valid_pixels == 8

    def test_whole_raster_is_half_cloud(self, scl_path):
        aoi = polygon_aoi(300000, 5999920, 300080, 6000000)

        stats = compute_cloud_fraction(scl_path, aoi)

        assert stats.cloud_fraction == 0.5
        assert stats.valid_pixels == 16
        assert stats.total_pixels == 16

    def test_point_without_buffer_raises(self, scl_path):
        aoi = AOI.from_shapely(Point(300040, 5999950), crs=CRS)

        with pytest.raises(ValueError, match="no area"):
            compute_cloud_fraction(scl_path, aoi)

    def test_point_with_buffer_over_cloudy_pixels(self, scl_path):
        # Center of pixel (row=3, col=1), a cloudy (class 9) pixel; a small
        # buffer keeps the clip comfortably inside that single 20m pixel
        # without straddling a neighboring pixel's boundary.
        aoi = AOI.from_shapely(Point(300030, 5999930), crs=CRS)

        stats = compute_cloud_fraction(scl_path, aoi, buffer_meters=5)

        assert stats.cloud_fraction == 1.0

    def test_custom_cloud_classes_narrows_the_definition(self, scl_path):
        aoi = polygon_aoi(300000, 5999920, 300080, 6000000)

        default_stats = compute_cloud_fraction(scl_path, aoi)
        narrow_stats = compute_cloud_fraction(scl_path, aoi, cloud_classes=frozenset({3}))

        assert default_stats.cloud_fraction == 0.5
        assert narrow_stats.cloud_fraction == 0.0

    def test_aoi_outside_raster_raises(self, scl_path):
        aoi = polygon_aoi(0, 0, 10, 10)

        with pytest.raises(ValueError):
            compute_cloud_fraction(scl_path, aoi)


class TestFindSclBand:
    def test_finds_the_band_under_a_safe_product_dir(self, tmp_path):
        expected = (
            tmp_path
            / "S2A_MSIL2A_20230115.SAFE"
            / "GRANULE"
            / "L2A_T18HXE_A039876_20230115T143751"
            / "IMG_DATA"
            / "R20m"
            / "T18HXE_20230115T143751_SCL_20m.jp2"
        )
        expected.parent.mkdir(parents=True)
        expected.touch()

        found = find_scl_band(tmp_path / "S2A_MSIL2A_20230115.SAFE")

        assert found == expected

    def test_raises_when_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            find_scl_band(tmp_path / "nonexistent.SAFE")
