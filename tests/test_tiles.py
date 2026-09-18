import requests
from pyproj import Transformer
from shapely.geometry import Point, Polygon, box

from downloader.geometry import AOI
from downloader.storage.repositories import TileFootprintRepository
from downloader.tiles.discovery import discover_candidate_tiles
from downloader.tiles.matcher import match_tiles

# Two adjacent Sentinel-2 tiles, shaped like the real API response
# (`Name` + `GeoFootprint`) captured against the live catalogue.
TILE_A_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [
        [[-71.3, -33.5], [-70.2, -33.5], [-70.2, -32.5], [-71.3, -32.5], [-71.3, -33.5]]
    ],
}
TILE_B_FOOTPRINT = {
    "type": "Polygon",
    "coordinates": [
        [[-70.3, -33.5], [-69.2, -33.5], [-69.2, -32.5], [-70.3, -32.5], [-70.3, -33.5]]
    ],
}


def fake_catalogue_response(*products):
    response = requests.Response()
    response.status_code = 200
    response._content = None
    response.json = lambda: {"value": list(products)}
    return response


def product(name, geo_footprint):
    return {"Name": name, "GeoFootprint": geo_footprint}


TWO_TILE_RESPONSE = fake_catalogue_response(
    product("S2A_MSIL2A_20230115T143751_N0509_R096_T19HCC_20230115T190229.SAFE", TILE_A_FOOTPRINT),
    product("S2B_MSIL2A_20230113T144729_N0509_R139_T19HCD_20230113T181834.SAFE", TILE_B_FOOTPRINT),
    # A second product for the same tile as the first - must be deduped.
    product("S2A_MSIL2A_20230105T143751_N0509_R096_T19HCC_20230105T190229.SAFE", TILE_A_FOOTPRINT),
)


class TestDiscoverCandidateTiles:
    def test_extracts_and_dedups_distinct_tiles(self, monkeypatch):
        monkeypatch.setattr(
            "downloader.tiles.discovery.requests.get",
            lambda *args, **kwargs: TWO_TILE_RESPONSE,
        )

        tiles = discover_candidate_tiles(box(-70.8, -33.2, -70.6, -33.0), crs="EPSG:4326")

        assert set(tiles.keys()) == {"T19HCC", "T19HCD"}
        assert tiles["T19HCC"].equals(Polygon(TILE_A_FOOTPRINT["coordinates"][0]))

    def test_ignores_products_without_a_recognizable_tile_id(self, monkeypatch):
        response = fake_catalogue_response(product("not-a-sentinel-name", TILE_A_FOOTPRINT))
        monkeypatch.setattr("downloader.tiles.discovery.requests.get", lambda *a, **k: response)

        tiles = discover_candidate_tiles(box(-70.8, -33.2, -70.6, -33.0), crs="EPSG:4326")

        assert tiles == {}


class TestMatchTiles:
    def test_offline_when_cache_has_an_intersecting_tile(self, tmp_path, monkeypatch):
        db_path = tmp_path / "sentinel.db"
        TileFootprintRepository(db_path).upsert(
            "T19HCC", Polygon(TILE_A_FOOTPRINT["coordinates"][0])
        )

        def fail_if_called(*args, **kwargs):
            raise AssertionError("should not query the network when the cache already has a hit")

        monkeypatch.setattr("downloader.tiles.discovery.requests.get", fail_if_called)

        aoi = AOI.from_geojson({"type": "Point", "coordinates": [-70.8, -33.0]})
        matches = match_tiles(aoi, db_path=db_path)

        assert [m.tile_id for m in matches] == ["T19HCC"]

    def test_offline_cache_hit_when_aoi_crs_is_not_wgs84(self, tmp_path, monkeypatch):
        # Cached footprints are always WGS84; the AOI here is a UTM point at
        # the same real-world location, inside TILE_A_FOOTPRINT's bounds -
        # the cache check must reproject to compare them correctly instead
        # of comparing raw coordinates from two different CRSes.
        db_path = tmp_path / "sentinel.db"
        TileFootprintRepository(db_path).upsert(
            "T19HCC", Polygon(TILE_A_FOOTPRINT["coordinates"][0])
        )

        def fail_if_called(*args, **kwargs):
            raise AssertionError("should not query the network when the cache already has a hit")

        monkeypatch.setattr("downloader.tiles.discovery.requests.get", fail_if_called)

        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32719", always_xy=True)
        utm_x, utm_y = transformer.transform(-70.75, -33.0)
        aoi = AOI.from_shapely(Point(utm_x, utm_y), crs="EPSG:32719")

        matches = match_tiles(aoi, db_path=db_path)

        assert [m.tile_id for m in matches] == ["T19HCC"]

    def test_cache_miss_queries_and_caches_the_discovered_tile(self, tmp_path, monkeypatch):
        db_path = tmp_path / "sentinel.db"
        monkeypatch.setattr(
            "downloader.tiles.discovery.requests.get",
            lambda *args, **kwargs: TWO_TILE_RESPONSE,
        )

        aoi = AOI.from_geojson({"type": "Point", "coordinates": [-70.8, -33.0]})
        matches = match_tiles(aoi, db_path=db_path)

        assert [m.tile_id for m in matches] == ["T19HCC"]
        # The discovered tile is now cached for next time.
        cached = TileFootprintRepository(db_path).get("T19HCC")
        assert cached is not None

    def test_returns_empty_list_when_nothing_intersects(self, tmp_path, monkeypatch):
        db_path = tmp_path / "sentinel.db"
        empty_response = fake_catalogue_response()
        monkeypatch.setattr(
            "downloader.tiles.discovery.requests.get", lambda *a, **k: empty_response
        )

        aoi = AOI.from_geojson({"type": "Point", "coordinates": [0.0, 0.0]})
        matches = match_tiles(aoi, db_path=db_path)

        assert matches == []

    def test_ranks_by_overlap_and_marks_full_containment(self, tmp_path):
        db_path = tmp_path / "sentinel.db"
        repository = TileFootprintRepository(db_path)
        # A small tile that fully contains the AOI, and a larger one that
        # only clips a corner of it.
        small_full_cover = Polygon([(-1, -1), (-1, 1), (1, 1), (1, -1)])
        large_partial_cover = Polygon([(0.2, 0.2), (0.2, 2), (2, 2), (2, 0.2)])
        repository.upsert("SMALL", small_full_cover)
        repository.upsert("LARGE", large_partial_cover)

        aoi = AOI.from_wkt(
            "POLYGON((-0.5 -0.5, -0.5 0.5, 0.5 0.5, 0.5 -0.5, -0.5 -0.5))", crs="EPSG:4326"
        )
        matches = match_tiles(aoi, db_path=db_path)

        assert [m.tile_id for m in matches] == ["SMALL", "LARGE"]
        assert matches[0].contains is True
        assert matches[0].overlap_fraction == 1.0
        assert 0 < matches[1].overlap_fraction < 1.0

    def test_point_aoi_overlap_is_binary(self, tmp_path):
        db_path = tmp_path / "sentinel.db"
        repository = TileFootprintRepository(db_path)
        repository.upsert("T", Polygon([(-1, -1), (-1, 1), (1, 1), (1, -1)]))

        aoi = AOI.from_shapely(Point(0, 0), crs="EPSG:4326")
        matches = match_tiles(aoi, db_path=db_path)

        assert matches[0].overlap_fraction == 1.0
        assert matches[0].contains is True
