import numpy as np
import pytest
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from downloader.best_image import NoCleanImageFoundError, find_best_image
from downloader.downloaders.s2_downloader import Sentinel2
from downloader.geometry import AOI
from downloader.models import Sentinel2DownloadStatus
from downloader.storage.repositories import TileFootprintRepository

TILE_ID = "T19HCC"
TILE_FOOTPRINT = Polygon([(-71.3, -33.5), (-70.2, -33.5), (-70.2, -32.5), (-71.3, -32.5)])

LON, LAT = -70.75, -33.0
AOI_POINT = AOI.from_geojson({"type": "Point", "coordinates": [LON, LAT]})
BUFFER_METERS = 5

_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32719", always_xy=True)
_UTM_X, _UTM_Y = _to_utm.transform(LON, LAT)
RASTER_CRS = "EPSG:32719"
# Origin chosen so (_UTM_X, _UTM_Y) sits at the center of pixel (row=1, col=1)
# in a 4x4, 20m grid - comfortably inside a pixel, not on a boundary.
_ORIGIN_X, _ORIGIN_Y = _UTM_X - 30, _UTM_Y + 30
SCL_TRANSFORM = from_origin(_ORIGIN_X, _ORIGIN_Y, 20, 20)
TCI_TRANSFORM = from_origin(_ORIGIN_X, _ORIGIN_Y, 10, 10)

CLEAR_SCL_CLASS = 4
CLOUD_SCL_CLASS = 9
NO_DATA_SCL_CLASS = 0


def fake_catalogue_response(products_by_offset: dict[int, str]):
    def make_product(product_id: str, date: str) -> dict:
        return {
            "Id": product_id,
            "Name": f"S2A_MSIL2A_{date.replace('-', '')}T143751_N0509_R096_{TILE_ID}_x.SAFE",
            "ContentDate": {"Start": f"{date}T14:37:51.024Z", "End": f"{date}T14:37:51.024Z"},
            "Online": True,
        }

    response = requests.Response()
    response.status_code = 200
    response.json = lambda: {
        "value": [make_product(pid, date) for pid, date in products_by_offset.items()]
    }
    return response


def write_band(product_dir, band_suffix, resolution_dir, transform, size, count, fill):
    path = product_dir / "GRANULE" / "G1" / "IMG_DATA" / resolution_dir / f"x_{band_suffix}.jp2"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.full((count, size, size), fill, dtype=np.uint8)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=count,
        dtype=np.uint8,
        crs=RASTER_CRS,
        transform=transform,
    ) as dst:
        dst.write(data)


def install_fake_download(monkeypatch, cloud_class_by_id, calls):
    def fake_download_product(self, product):
        calls.append(product.id)
        product_dir = self.output_dir / product.name
        write_band(
            product_dir, "SCL_20m", "R20m", SCL_TRANSFORM, 4, 1, cloud_class_by_id[product.id]
        )
        if "TCI_10m" in self.band_selection:
            write_band(product_dir, "TCI_10m", "R10m", TCI_TRANSFORM, 8, 3, 128)
        return Sentinel2DownloadStatus(product_id=product.id, product_name=product.name)

    monkeypatch.setattr(Sentinel2, "download_product", fake_download_product)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "sentinel.db"
    TileFootprintRepository(path).upsert(TILE_ID, TILE_FOOTPRINT)
    return path


def call_find_best_image(db_path, output_dir, **kwargs):
    # A 10-day window around the 15th keeps candidate dates inside June,
    # so process_dates never splits it into more than one calendar-month
    # chunk - the fake catalogue response below returns a fixed product set
    # regardless of the query, so it isn't a stand-in for a real per-chunk
    # date filter and would otherwise be "returned" once per chunk.
    kwargs.setdefault("search_window_days", 10)
    return find_best_image(
        AOI_POINT,
        "2023-06-15",
        username="test",
        password="test",
        buffer_meters=BUFFER_METERS,
        db_path=db_path,
        output_dir=output_dir,
        **kwargs,
    )


class TestFindBestImage:
    def test_nearest_clean_candidate_wins_without_checking_others(
        self, tmp_path, db_path, monkeypatch
    ):
        # offsets relative to the target date 2023-06-15
        products = {"near": "2023-06-15", "far-a": "2023-06-10", "far-b": "2023-06-20"}
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response(products),
        )
        cloud_class_by_id = {
            "near": CLEAR_SCL_CLASS,
            "far-a": CLOUD_SCL_CLASS,
            "far-b": CLOUD_SCL_CLASS,
        }
        calls: list[str] = []
        install_fake_download(monkeypatch, cloud_class_by_id, calls)

        result = call_find_best_image(db_path, tmp_path / "out")

        assert result.product.id == "near"
        assert result.tile_id == TILE_ID
        assert result.cloud_stats.cloud_fraction == 0.0
        # Only the winner was ever downloaded: once for the SCL check, once
        # more (with TCI added) after it won - the other candidates were
        # never touched.
        assert calls == ["near", "near"]

    def test_cloudy_nearest_is_skipped_for_a_clean_later_candidate(
        self, tmp_path, db_path, monkeypatch
    ):
        products = {"near": "2023-06-15", "later": "2023-06-18"}
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response(products),
        )
        cloud_class_by_id = {"near": CLOUD_SCL_CLASS, "later": CLEAR_SCL_CLASS}
        calls: list[str] = []
        install_fake_download(monkeypatch, cloud_class_by_id, calls)

        result = call_find_best_image(db_path, tmp_path / "out")

        assert result.product.id == "later"
        assert calls == ["near", "later", "later"]

    def test_candidate_with_no_aoi_coverage_is_skipped_not_fatal(
        self, tmp_path, db_path, monkeypatch
    ):
        # A real occurrence: a partial/edge-of-swath acquisition can have
        # NO_DATA (class 0) over the whole AOI for one candidate date, while
        # a nearby date has real coverage. That must be skipped like a
        # failed download, not crash the whole search.
        products = {"no-coverage": "2023-06-15", "clean": "2023-06-17"}
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response(products),
        )
        cloud_class_by_id = {"no-coverage": NO_DATA_SCL_CLASS, "clean": CLEAR_SCL_CLASS}
        calls: list[str] = []
        install_fake_download(monkeypatch, cloud_class_by_id, calls)

        result = call_find_best_image(db_path, tmp_path / "out")

        assert result.product.id == "clean"
        assert calls == ["no-coverage", "clean", "clean"]

    def test_saves_a_real_jpg(self, tmp_path, db_path, monkeypatch):
        products = {"near": "2023-06-15"}
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response(products),
        )
        install_fake_download(monkeypatch, {"near": CLEAR_SCL_CLASS}, [])

        result = call_find_best_image(db_path, tmp_path / "out")

        assert result.image_path is not None
        assert result.image_path.exists()
        assert result.image_path.stat().st_size > 0

    def test_raises_when_nothing_meets_the_threshold(self, tmp_path, db_path, monkeypatch):
        products = {"a": "2023-06-14", "b": "2023-06-16"}
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response(products),
        )
        install_fake_download(monkeypatch, {"a": CLOUD_SCL_CLASS, "b": CLOUD_SCL_CLASS}, [])

        with pytest.raises(NoCleanImageFoundError, match="checked 2"):
            call_find_best_image(db_path, tmp_path / "out")

    def test_raises_when_no_candidates_at_all(self, tmp_path, db_path, monkeypatch):
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response({}),
        )

        with pytest.raises(ValueError, match="No Sentinel-2 products found"):
            call_find_best_image(db_path, tmp_path / "out")

    def test_raises_when_no_tile_intersects_the_aoi(self, tmp_path, monkeypatch):
        empty_db = tmp_path / "empty.db"
        far_away_aoi = AOI.from_geojson({"type": "Point", "coordinates": [0.0, 0.0]})
        # Cache is empty, so match_tiles falls back to discovery - keep that
        # offline too, since this test is only about the "nothing found" path.
        monkeypatch.setattr(
            "downloader.tiles.discovery.requests.get",
            lambda *a, **k: fake_catalogue_response({}),
        )

        with pytest.raises(ValueError, match="No Sentinel-2 tile intersects"):
            find_best_image(
                far_away_aoi,
                "2023-06-15",
                username="test",
                password="test",
                db_path=empty_db,
                output_dir=tmp_path / "out",
            )
