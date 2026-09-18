import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from downloader.geometry import AOI
from downloader.rasters import clip_raster, crop_image, crop_window

CRS = "EPSG:32718"  # UTM zone 18S, matches the project's Chile-based test data.

# A 4x4, 10m-pixel, 3-band raster mimicking a TCI RGB crop. Origin
# (300000, 6000000). Each band has a distinct, position-dependent value so a
# crop's content is easy to assert on: value = row * 10 + col.
_TRANSFORM = from_origin(300000, 6000000, 10, 10)
_ROW_COL_VALUES = np.array(
    [[row * 10 + col for col in range(4)] for row in range(4)],
    dtype=np.uint8,
)
_TCI_DATA = np.stack([_ROW_COL_VALUES, _ROW_COL_VALUES + 1, _ROW_COL_VALUES + 2])


@pytest.fixture
def tci_path(tmp_path):
    path = tmp_path / "T18HXE_20230115T143751_TCI_10m.jp2"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",  # content format doesn't matter to rasterio once opened
        height=4,
        width=4,
        count=3,
        dtype=np.uint8,
        crs=CRS,
        transform=_TRANSFORM,
    ) as dst:
        dst.write(_TCI_DATA)
    return path


def polygon_aoi(*bounds):
    return AOI.from_shapely(box(*bounds), crs=CRS)


class TestClipRaster:
    def test_clips_to_the_requested_sub_region(self, tci_path):
        # Rows 0-1, cols 0-1: top-left quadrant.
        aoi = polygon_aoi(300000, 5999980, 300020, 6000000)

        clipped, profile = clip_raster(tci_path, aoi)

        assert clipped.shape == (3, 2, 2)
        np.testing.assert_array_equal(clipped[0], _ROW_COL_VALUES[0:2, 0:2])
        assert profile["height"] == 2
        assert profile["width"] == 2

    def test_transform_reflects_the_crop_not_the_full_extent(self, tci_path):
        aoi = polygon_aoi(300000, 5999980, 300020, 6000000)

        _, profile = clip_raster(tci_path, aoi)

        # The crop's origin should still be (300000, 6000000) - it starts
        # at the same top-left corner as the requested sub-region.
        assert profile["transform"] * (0, 0) == (300000, 6000000)

    def test_point_without_buffer_raises(self, tci_path):
        aoi = AOI.from_shapely(Point(300005, 5999995), crs=CRS)

        with pytest.raises(ValueError, match="no area"):
            clip_raster(tci_path, aoi)

    def test_aoi_outside_raster_raises(self, tci_path):
        aoi = polygon_aoi(0, 0, 10, 10)

        with pytest.raises(ValueError):
            clip_raster(tci_path, aoi)


class TestCropImage:
    def test_without_output_path_returns_data_only(self, tci_path):
        aoi = polygon_aoi(300000, 5999980, 300020, 6000000)

        result = crop_image(tci_path, aoi)

        assert result.output_path is None
        assert result.data.shape == (3, 2, 2)
        assert result.crs.to_epsg() == 32718

    def test_with_output_path_writes_a_readable_geotiff(self, tmp_path, tci_path):
        aoi = polygon_aoi(300000, 5999980, 300020, 6000000)
        output_path = tmp_path / "cropped.tif"

        result = crop_image(tci_path, aoi, output_path=output_path)

        assert result.output_path == output_path
        assert output_path.exists()

        with rasterio.open(output_path) as written:
            assert written.driver == "GTiff"
            assert written.count == 3
            assert written.crs.to_epsg() == 32718
            np.testing.assert_array_equal(written.read(), result.data)

    def test_creates_missing_output_parent_directories(self, tmp_path, tci_path):
        aoi = polygon_aoi(300000, 5999980, 300020, 6000000)
        output_path = tmp_path / "nested" / "dir" / "cropped.tif"

        result = crop_image(tci_path, aoi, output_path=output_path)

        assert result.output_path.exists()


class TestCropWindow:
    # The fixture raster is 4x4 at 10m, origin (300000, 6000000). Windows below
    # are chosen so their edges fall mid-pixel, never exactly on a pixel border.
    SMALL_POLYGON = (300012, 5999982, 300018, 5999988)  # sits inside pixel (row 1, col 1)

    def test_grows_by_meters_and_is_square(self, tci_path):
        result = crop_window(tci_path, polygon_aoi(*self.SMALL_POLYGON), meters=3.5)

        assert result.data.shape == (3, 3, 3)
        assert result.transform * (0, 0) == (300000, 6000000)

    def test_square_makes_a_wide_polygon_window_square(self, tci_path):
        wide = polygon_aoi(300005, 5999982, 300025, 5999988)  # 20m wide, 6m tall

        squared = crop_window(tci_path, wide, meters=0)
        natural = crop_window(tci_path, wide, meters=0, square=False)

        assert squared.data.shape == (3, 3, 3)
        assert natural.data.shape == (3, 1, 3)

    def test_point_gets_a_square_window_of_meters(self, tci_path):
        point = AOI.from_shapely(Point(300015, 5999985), crs=CRS)

        result = crop_window(tci_path, point, meters=12)

        assert result.data.shape == (3, 3, 3)

    def test_window_is_clamped_to_the_raster(self, tci_path):
        result = crop_window(tci_path, polygon_aoi(*self.SMALL_POLYGON), meters=1000)

        assert result.data.shape == (3, 4, 4)

    def test_filled_shows_real_imagery_everywhere(self, tci_path):
        result = crop_window(tci_path, polygon_aoi(*self.SMALL_POLYGON), meters=3.5)

        # Band 1 is row * 10 + col + 1, so it's nonzero for every real pixel.
        assert (result.data[1] > 0).all()

    def test_not_filled_blanks_everything_outside_the_polygon(self, tci_path):
        result = crop_window(tci_path, polygon_aoi(*self.SMALL_POLYGON), meters=3.5, filled=False)

        assert result.data[:, 1, 1].tolist() == [11, 12, 13]
        assert np.count_nonzero(result.data[0]) == 1

    def test_reprojects_a_wgs84_aoi_into_the_raster_crs(self, tci_path):
        lon, lat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(300015, 5999985)
        point = AOI.from_shapely(Point(lon, lat), crs="EPSG:4326")

        result = crop_window(tci_path, point, meters=12)

        assert result.data.shape == (3, 3, 3)

    def test_writes_a_geotiff_when_given_an_output_path(self, tmp_path, tci_path):
        output_path = tmp_path / "window.tif"

        result = crop_window(
            tci_path, polygon_aoi(*self.SMALL_POLYGON), meters=3.5, output_path=output_path
        )

        with rasterio.open(output_path) as written:
            assert written.driver == "GTiff"
            np.testing.assert_array_equal(written.read(), result.data)

    def test_window_outside_the_raster_raises(self, tci_path):
        with pytest.raises(ValueError):
            crop_window(tci_path, polygon_aoi(0, 0, 10, 10), meters=5)
