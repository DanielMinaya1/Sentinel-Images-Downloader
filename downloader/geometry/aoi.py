"""
A single, consistent AOI (area of interest) representation for
geometry-focused features: tile matching, AOI-scoped cloud
filtering, cropping, time series, and best-image selection all accept an
`AOI` regardless of where it originally came from.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import geopandas as gpd
import shapely.wkt
from pyproj import CRS
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from downloader.geometry.crs import estimate_metric_crs, reproject

type CRSLike = str | int | CRS


class GeometryKind(Enum):
    POINT = "point"
    LINE = "line"
    POLYGON = "polygon"


_KIND_BY_GEOM_TYPE = {
    "Point": GeometryKind.POINT,
    "MultiPoint": GeometryKind.POINT,
    "LineString": GeometryKind.LINE,
    "MultiLineString": GeometryKind.LINE,
    "LinearRing": GeometryKind.LINE,
    "Polygon": GeometryKind.POLYGON,
    "MultiPolygon": GeometryKind.POLYGON,
}


@dataclass
class AOI:
    """An area of interest: a shapely geometry paired with its CRS.

    Multi-part geometries (MultiPolygon/MultiLineString/MultiPoint) are a
    single AOI of the corresponding kind, same as their single counterpart -
    shapely's buffer/intersects/intersection/area all operate on them
    natively. An AOI is never implicitly split into several; "many AOIs"
    only comes from the input layer (e.g. one row per AOI in a GeoDataFrame).
    """

    geometry: BaseGeometry
    crs: CRS
    kind: GeometryKind = field(init=False)

    def __post_init__(self) -> None:
        try:
            self.kind = _KIND_BY_GEOM_TYPE[self.geometry.geom_type]
        except KeyError:
            raise ValueError(
                f"Unsupported geometry type for an AOI: {self.geometry.geom_type!r}"
            ) from None

    @classmethod
    def from_shapely(cls, geometry: BaseGeometry, crs: CRSLike) -> "AOI":
        return cls(geometry=geometry, crs=CRS.from_user_input(crs))

    @classmethod
    def from_geojson(cls, data: dict[str, Any], crs: CRSLike = "EPSG:4326") -> "AOI":
        """`data` may be a bare geometry dict or a Feature dict (its `"geometry"` is used).

        Defaults to EPSG:4326 per the GeoJSON spec (RFC 7946).
        """
        geometry_data = data["geometry"] if data.get("type") == "Feature" else data
        return cls.from_shapely(shape(geometry_data), crs)

    @classmethod
    def from_wkt(cls, wkt: str, crs: CRSLike) -> "AOI":
        return cls.from_shapely(shapely.wkt.loads(wkt), crs)

    @classmethod
    def from_geoseries(cls, series: gpd.GeoSeries) -> list["AOI"]:
        """One `AOI` per row, carrying the series' CRS."""
        return [cls.from_shapely(geometry, series.crs) for geometry in series]

    @classmethod
    def from_geodataframe(cls, gdf: gpd.GeoDataFrame, geom_col: str = "geometry") -> list["AOI"]:
        return cls.from_geoseries(gdf[geom_col])

    @classmethod
    def from_postgis(
        cls,
        sql: str,
        con: Any,
        geom_col: str = "geom",
        crs: CRSLike | None = None,
    ) -> list["AOI"]:
        """`con` is a caller-supplied SQLAlchemy connectable, same as `geopandas.read_postgis`."""
        gdf = gpd.read_postgis(sql, con, geom_col=geom_col, crs=crs)
        return cls.from_geodataframe(gdf, geom_col)

    def to_polygon(
        self,
        buffer_meters: float | None = None,
        crs: CRSLike | None = None,
    ) -> BaseGeometry:
        """
        Returns a polygon for this AOI, buffered by `buffer_meters` if given.

        A POINT/LINE-kind AOI has no area of its own, so `buffer_meters` is
        required for those; a POLYGON-kind AOI can be returned as-is.
        Buffering reprojects to an estimated metric CRS first (buffering in
        raw EPSG:4326 degrees distorts distances by latitude), then to `crs`
        if given, else back to this AOI's own CRS.
        """
        if buffer_meters is None and self.kind is not GeometryKind.POLYGON:
            raise ValueError(
                f"A {self.kind.value} AOI has no area; pass buffer_meters to get a polygon."
            )

        geometry, working_crs = self.geometry, self.crs
        if buffer_meters is not None:
            metric_crs = estimate_metric_crs(geometry, working_crs)
            geometry = reproject(geometry, working_crs, metric_crs).buffer(buffer_meters)
            working_crs = metric_crs

        if crs is not None:
            target_crs = CRS.from_user_input(crs)
            if target_crs != working_crs:
                geometry = reproject(geometry, working_crs, target_crs)

        return geometry
