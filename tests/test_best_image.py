from pathlib import Path

import numpy as np
import pytest
import rasterio
import requests
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box

from downloader.best_image import NoCleanImageFoundError, find_best_image, find_best_image_in_range
from downloader.downloaders.s2_downloader import Sentinel2
from downloader.geometry import AOI
from downloader.models import DownloadStatus, FileDownloadResult, Sentinel2DownloadStatus
from downloader.storage.repositories import TileFootprintRepository
from downloader.visualization import ImageOptions

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
# A polygon covering all 16 pixel centers of the 4x4 SCL grid, so a product's
# cloud fraction is simply (cloudy pixels / 16).
WHOLE_RASTER_AOI = AOI.from_shapely(
    box(_ORIGIN_X + 1, _ORIGIN_Y - 79, _ORIGIN_X + 79, _ORIGIN_Y - 1), crs="EPSG:32719"
)

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


def cloudy_pixels(count):
    """A 4x4 SCL grid whose first `count` pixels (row-major) are cloud, the rest clear."""
    flat = np.full(16, CLEAR_SCL_CLASS, dtype=np.uint8)
    flat[:count] = CLOUD_SCL_CLASS
    return flat.reshape(4, 4)


def write_band(product_dir, band_suffix, resolution_dir, transform, data):
    path = product_dir / "GRANULE" / "G1" / "IMG_DATA" / resolution_dir / f"x_{band_suffix}.jp2"
    path.parent.mkdir(parents=True, exist_ok=True)
    _, height, width = data.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=data.shape[0],
        dtype=np.uint8,
        crs=RASTER_CRS,
        transform=transform,
    ) as dst:
        dst.write(data)


def install_fake_download(monkeypatch, scl_by_id, calls, *, failing_ids=(), work_dirs=None):
    """
    Fakes `Sentinel2.download_product`: writes a synthetic SCL band (an int
    fills the whole grid, a 4x4 array is used as-is) and, once TCI is
    requested, a synthetic TCI band, into the downloader's output dir.
    """

    def fake_download_product(self, product):
        calls.append(product.id)
        if work_dirs is not None:
            work_dirs.append(self.output_dir)

        if product.id in failing_ids:
            failed_file = FileDownloadResult(
                Path("x_SCL_20m.jp2"), DownloadStatus.FAILED, error="boom"
            )
            return Sentinel2DownloadStatus(
                product_id=product.id, product_name=product.name, files=[failed_file]
            )

        product_dir = self.output_dir / product.name
        scl = np.asarray(scl_by_id[product.id])
        scl = np.full((4, 4), scl, dtype=np.uint8) if scl.ndim == 0 else scl.astype(np.uint8)
        write_band(product_dir, "SCL_20m", "R20m", SCL_TRANSFORM, scl[None])
        if "TCI_10m" in self.band_selection:
            tci = np.full((3, 8, 8), 128, dtype=np.uint8)
            write_band(product_dir, "TCI_10m", "R10m", TCI_TRANSFORM, tci)
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

    def test_candidate_whose_scl_download_failed_is_skipped(self, tmp_path, db_path, monkeypatch):
        # A file-level download failure (retries exhausted) leaves no
        # status.error, only a FAILED file - it must still be skipped.
        products = {"flaky": "2023-06-15", "ok": "2023-06-17"}
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response(products),
        )
        calls: list[str] = []
        install_fake_download(
            monkeypatch,
            {"flaky": CLEAR_SCL_CLASS, "ok": CLEAR_SCL_CLASS},
            calls,
            failing_ids={"flaky"},
        )

        result = call_find_best_image(db_path, tmp_path / "out")

        assert result.product.id == "ok"


def call_range(db_path, output_dir, geometry=WHOLE_RASTER_AOI, **kwargs):
    # June 5-25 stays inside one calendar-month chunk of process_dates, for
    # the same reason as in call_find_best_image above.
    return find_best_image_in_range(
        geometry,
        "2023-06-05",
        "2023-06-25",
        output_dir,
        username="test",
        password="test",
        db_path=db_path,
        **kwargs,
    )


class TestFindBestImageInRange:
    def patch_catalogue(self, monkeypatch, products):
        monkeypatch.setattr(
            "downloader.best_image.requests.get",
            lambda *a, **k: fake_catalogue_response(products),
        )

    def test_clearest_picks_the_lowest_cloud_candidate_across_the_range(
        self, tmp_path, db_path, monkeypatch
    ):
        self.patch_catalogue(
            monkeypatch, {"half": "2023-06-08", "quarter": "2023-06-12", "most": "2023-06-20"}
        )
        calls: list[str] = []
        install_fake_download(
            monkeypatch,
            {"half": cloudy_pixels(8), "quarter": cloudy_pixels(4), "most": cloudy_pixels(12)},
            calls,
        )

        result = call_range(db_path, tmp_path / "out", max_cloud_fraction=0.3, prefer="clearest")

        assert result.product.id == "quarter"
        assert result.cloud_stats.cloud_fraction == 0.25
        # Every candidate's SCL was checked (most recent first), then only
        # the winner was downloaded again for TCI.
        assert calls == ["most", "quarter", "half", "quarter"]

    def test_partial_no_data_coverage_counts_against_a_candidate(
        self, tmp_path, db_path, monkeypatch
    ):
        # Newest date is "clear" only over the few pixels the swath covers
        # (the rest is NO_DATA), so it must lose to the fully covered one.
        self.patch_catalogue(monkeypatch, {"partial": "2023-06-20", "full": "2023-06-10"})
        partial = np.full(16, NO_DATA_SCL_CLASS, dtype=np.uint8)
        partial[:4] = CLEAR_SCL_CLASS
        install_fake_download(
            monkeypatch,
            {"partial": partial.reshape(4, 4), "full": CLEAR_SCL_CLASS},
            [],
        )

        result = call_range(db_path, tmp_path / "out")

        assert result.product.id == "full"

    def test_stops_at_the_first_perfectly_clear_candidate_most_recent_first(
        self, tmp_path, db_path, monkeypatch
    ):
        self.patch_catalogue(
            monkeypatch, {"old-clear": "2023-06-08", "new-clear": "2023-06-20", "mid": "2023-06-14"}
        )
        calls: list[str] = []
        install_fake_download(
            monkeypatch,
            {"old-clear": CLEAR_SCL_CLASS, "new-clear": CLEAR_SCL_CLASS, "mid": cloudy_pixels(2)},
            calls,
        )

        result = call_range(db_path, tmp_path / "out")

        assert result.product.id == "new-clear"
        assert result.cloud_stats.cloud_fraction == 0.0
        assert calls == ["new-clear", "new-clear"]

    def test_recent_takes_the_newest_qualifying_date_even_if_an_older_one_is_clearer(
        self, tmp_path, db_path, monkeypatch
    ):
        # newest is 1/16 = 6.25% cloud, older is perfectly clear; with a 10%
        # tolerance the newest is "clear enough", so it wins without ever
        # checking the older one.
        self.patch_catalogue(monkeypatch, {"newest": "2023-06-20", "older": "2023-06-10"})
        calls: list[str] = []
        install_fake_download(
            monkeypatch, {"newest": cloudy_pixels(1), "older": CLEAR_SCL_CLASS}, calls
        )

        result = call_range(db_path, tmp_path / "out", max_cloud_fraction=0.1)

        assert result.product.id == "newest"
        assert calls == ["newest", "newest"]

    def test_recent_skips_a_too_cloudy_newest_for_the_next_qualifying_date(
        self, tmp_path, db_path, monkeypatch
    ):
        self.patch_catalogue(
            monkeypatch, {"cloudy": "2023-06-22", "ok": "2023-06-15", "older-ok": "2023-06-08"}
        )
        calls: list[str] = []
        install_fake_download(
            monkeypatch,
            {"cloudy": cloudy_pixels(8), "ok": cloudy_pixels(1), "older-ok": CLEAR_SCL_CLASS},
            calls,
        )

        result = call_range(db_path, tmp_path / "out", max_cloud_fraction=0.1)

        assert result.product.id == "ok"
        assert calls == ["cloudy", "ok", "ok"]

    def test_clearest_prefers_a_clearer_older_date_over_a_newer_qualifying_one(
        self, tmp_path, db_path, monkeypatch
    ):
        self.patch_catalogue(monkeypatch, {"newest": "2023-06-20", "older": "2023-06-10"})
        install_fake_download(
            monkeypatch, {"newest": cloudy_pixels(1), "older": CLEAR_SCL_CLASS}, []
        )

        result = call_range(db_path, tmp_path / "out", max_cloud_fraction=0.1, prefer="clearest")

        assert result.product.id == "older"

    def test_default_tolerates_a_few_percent_of_cloud(self, tmp_path, db_path, monkeypatch):
        # Default threshold is 5%; 1 cloudy pixel of 16 is 6.25%, just over it.
        self.patch_catalogue(monkeypatch, {"a": "2023-06-10"})
        install_fake_download(monkeypatch, {"a": cloudy_pixels(1)}, [])

        assert call_range(db_path, tmp_path / "out") is None

    def test_rejects_an_unknown_prefer_value(self, tmp_path, db_path):
        with pytest.raises(ValueError, match="prefer must be"):
            call_range(db_path, tmp_path / "out", prefer="newest")

    def test_returns_none_when_the_best_image_is_not_cloud_free_enough(
        self, tmp_path, db_path, monkeypatch
    ):
        self.patch_catalogue(monkeypatch, {"a": "2023-06-10", "b": "2023-06-20"})
        calls: list[str] = []
        install_fake_download(monkeypatch, {"a": cloudy_pixels(1), "b": cloudy_pixels(5)}, calls)
        output_dir = tmp_path / "out"

        result = call_range(db_path, output_dir)  # default: no clouds at all

        assert result is None
        # No TCI was ever downloaded and nothing was saved.
        assert calls == ["b", "a"]
        assert not output_dir.exists()

    def test_max_cloud_fraction_loosens_the_requirement(self, tmp_path, db_path, monkeypatch):
        self.patch_catalogue(monkeypatch, {"a": "2023-06-10"})
        install_fake_download(monkeypatch, {"a": cloudy_pixels(1)}, [])

        result = call_range(db_path, tmp_path / "out", max_cloud_fraction=0.1)

        assert result is not None
        assert result.cloud_stats.cloud_fraction == 1 / 16

    def test_returns_none_when_the_range_has_no_products(self, tmp_path, db_path, monkeypatch):
        self.patch_catalogue(monkeypatch, {})

        assert call_range(db_path, tmp_path / "out") is None

    def test_returns_none_when_no_candidate_is_usable(self, tmp_path, db_path, monkeypatch):
        self.patch_catalogue(monkeypatch, {"empty": "2023-06-10", "flaky": "2023-06-12"})
        install_fake_download(
            monkeypatch,
            {"empty": NO_DATA_SCL_CLASS, "flaky": CLEAR_SCL_CLASS},
            [],
            failing_ids={"flaky"},
        )

        assert call_range(db_path, tmp_path / "out") is None

    def test_accepts_a_geojson_dict_geometry(self, tmp_path, db_path, monkeypatch):
        self.patch_catalogue(monkeypatch, {"clear": "2023-06-10"})
        install_fake_download(monkeypatch, {"clear": CLEAR_SCL_CLASS}, [])
        geojson_polygon = {
            "type": "Polygon",
            "coordinates": [
                [
                    [LON - 0.0003, LAT - 0.0003],
                    [LON + 0.0003, LAT - 0.0003],
                    [LON + 0.0003, LAT + 0.0003],
                    [LON - 0.0003, LAT + 0.0003],
                    [LON - 0.0003, LAT - 0.0003],
                ]
            ],
        }

        result = call_range(db_path, tmp_path / "out", geometry=geojson_polygon)

        assert result is not None
        assert result.image_path.exists()

    def test_only_the_image_is_left_in_output_dir_by_default(self, tmp_path, db_path, monkeypatch):
        self.patch_catalogue(monkeypatch, {"clear": "2023-06-10"})
        work_dirs: list[Path] = []
        install_fake_download(monkeypatch, {"clear": CLEAR_SCL_CLASS}, [], work_dirs=work_dirs)
        output_dir = tmp_path / "out"

        result = call_range(db_path, output_dir)

        assert list(output_dir.iterdir()) == [result.image_path]
        assert result.image_path.stat().st_size > 0
        # The raw download went to a temporary directory that's now gone.
        assert work_dirs and not work_dirs[0].exists()

    def test_download_dir_keeps_the_raw_data(self, tmp_path, db_path, monkeypatch):
        self.patch_catalogue(monkeypatch, {"clear": "2023-06-10"})
        install_fake_download(monkeypatch, {"clear": CLEAR_SCL_CLASS}, [])
        download_dir = tmp_path / "raw"

        result = call_range(db_path, tmp_path / "out", download_dir=download_dir)

        assert (download_dir / result.product.name).is_dir()

    def test_image_options_control_the_saved_image(self, tmp_path, db_path, monkeypatch):
        self.patch_catalogue(monkeypatch, {"clear": "2023-06-10"})
        install_fake_download(monkeypatch, {"clear": CLEAR_SCL_CLASS}, [])

        result = call_range(
            db_path,
            tmp_path / "out",
            image_options=ImageOptions(meters=20, extension="png", figsize=(3, 3), dpi=40),
        )

        assert result.image_path.suffix == ".png"
        assert result.image_path.stat().st_size > 0

    def test_rejects_a_reversed_range(self, tmp_path, db_path):
        with pytest.raises(ValueError, match="on or before"):
            find_best_image_in_range(
                WHOLE_RASTER_AOI,
                "2023-06-25",
                "2023-06-05",
                tmp_path / "out",
                username="test",
                password="test",
                db_path=db_path,
            )

    def test_raises_when_no_tile_intersects_the_geometry(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "downloader.tiles.discovery.requests.get",
            lambda *a, **k: fake_catalogue_response({}),
        )
        far_away = AOI.from_geojson({"type": "Point", "coordinates": [0.0, 0.0]})

        with pytest.raises(ValueError, match="No Sentinel-2 tile intersects"):
            call_range(tmp_path / "empty.db", tmp_path / "out", geometry=far_away)
