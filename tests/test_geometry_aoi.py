import math

import geopandas as gpd
import pytest
from shapely.geometry import GeometryCollection, LineString, Point, Polygon

from downloader.geometry import AOI, GeometryKind

SANTIAGO_POINT = {"type": "Point", "coordinates": [-70.65, -33.45]}
A_LINE_WKT = "LINESTRING(-70.65 -33.45, -70.60 -33.40)"
A_POLYGON_WKT = "POLYGON((-70.7 -33.5, -70.7 -33.4, -70.6 -33.4, -70.6 -33.5, -70.7 -33.5))"


class TestFromGeojson:
    def test_bare_geometry_dict(self):
        aoi = AOI.from_geojson(SANTIAGO_POINT)

        assert aoi.kind == GeometryKind.POINT
        assert aoi.crs.to_epsg() == 4326

    def test_feature_dict_unwraps_geometry(self):
        feature = {"type": "Feature", "geometry": SANTIAGO_POINT, "properties": {"name": "x"}}

        aoi = AOI.from_geojson(feature)

        assert aoi.kind == GeometryKind.POINT

    def test_polygon_kind(self):
        aoi = AOI.from_geojson(
            {
                "type": "Polygon",
                "coordinates": [[[-70.7, -33.5], [-70.7, -33.4], [-70.6, -33.4], [-70.7, -33.5]]],
            }
        )

        assert aoi.kind == GeometryKind.POLYGON

    def test_custom_crs(self):
        aoi = AOI.from_geojson(SANTIAGO_POINT, crs="EPSG:3857")

        assert aoi.crs.to_epsg() == 3857


class TestFromWkt:
    def test_line_kind(self):
        aoi = AOI.from_wkt(A_LINE_WKT, crs="EPSG:4326")

        assert aoi.kind == GeometryKind.LINE

    def test_polygon_kind(self):
        aoi = AOI.from_wkt(A_POLYGON_WKT, crs="EPSG:4326")

        assert aoi.kind == GeometryKind.POLYGON


class TestFromShapely:
    def test_unsupported_geometry_raises(self):
        collection = GeometryCollection([Point(0, 0), LineString([(0, 0), (1, 1)])])

        with pytest.raises(ValueError, match="Unsupported geometry type"):
            AOI.from_shapely(collection, crs="EPSG:4326")


class TestFromGeoSeriesAndGeoDataFrame:
    def make_geodataframe(self):
        return gpd.GeoDataFrame(
            {"name": ["a", "b", "c"]},
            geometry=[
                Point(-70.65, -33.45),
                LineString([(-70.65, -33.45), (-70.60, -33.40)]),
                Polygon([(-70.7, -33.5), (-70.7, -33.4), (-70.6, -33.4)]),
            ],
            crs="EPSG:4326",
        )

    def test_from_geoseries_returns_one_aoi_per_row(self):
        gdf = self.make_geodataframe()

        aois = AOI.from_geoseries(gdf.geometry)

        assert [aoi.kind for aoi in aois] == [
            GeometryKind.POINT,
            GeometryKind.LINE,
            GeometryKind.POLYGON,
        ]
        assert all(aoi.crs.to_epsg() == 4326 for aoi in aois)

    def test_from_geodataframe_delegates_to_geoseries(self):
        gdf = self.make_geodataframe()

        aois = AOI.from_geodataframe(gdf)

        assert len(aois) == 3


class TestFromPostgis:
    def test_delegates_to_read_postgis_and_geodataframe(self, monkeypatch):
        gdf = gpd.GeoDataFrame(
            {"geom": [Point(-70.65, -33.45)]},
            geometry="geom",
            crs="EPSG:4326",
        )
        captured = {}

        def fake_read_postgis(sql, con, geom_col="geom", crs=None):
            captured["sql"] = sql
            captured["con"] = con
            captured["geom_col"] = geom_col
            return gdf

        monkeypatch.setattr("downloader.geometry.aoi.gpd.read_postgis", fake_read_postgis)

        aois = AOI.from_postgis("SELECT * FROM aois", con="fake-connection", geom_col="geom")

        assert captured["sql"] == "SELECT * FROM aois"
        assert captured["con"] == "fake-connection"
        assert captured["geom_col"] == "geom"
        assert len(aois) == 1
        assert aois[0].kind == GeometryKind.POINT


class TestToPolygon:
    def test_polygon_without_buffer_returns_own_geometry(self):
        aoi = AOI.from_wkt(A_POLYGON_WKT, crs="EPSG:4326")

        polygon = aoi.to_polygon()

        assert polygon.equals(aoi.geometry)

    def test_point_without_buffer_raises(self):
        aoi = AOI.from_geojson(SANTIAGO_POINT)

        with pytest.raises(ValueError, match="no area"):
            aoi.to_polygon()

    def test_line_without_buffer_raises(self):
        aoi = AOI.from_wkt(A_LINE_WKT, crs="EPSG:4326")

        with pytest.raises(ValueError, match="no area"):
            aoi.to_polygon()

    def test_point_buffer_area_matches_metric_circle(self):
        aoi = AOI.from_geojson(SANTIAGO_POINT)

        polygon = aoi.to_polygon(buffer_meters=1000)

        expected_area = math.pi * 1000**2
        assert polygon.area == pytest.approx(expected_area, rel=0.01)

    def test_crs_reprojects_the_result(self):
        aoi = AOI.from_geojson(SANTIAGO_POINT)

        polygon = aoi.to_polygon(buffer_meters=1000, crs="EPSG:4326")

        # Reprojected back to degrees: area is tiny compared to the metric one.
        assert polygon.area < 1
