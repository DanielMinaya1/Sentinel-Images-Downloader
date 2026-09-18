"""
CRS-aware helpers for `AOI.to_polygon()`.

Reprojection is delegated to geopandas' own `GeoSeries.to_crs()`/
`estimate_utm_crs()` machinery (round-tripping through a throwaway
single-item `GeoSeries`) rather than hand-rolling a `pyproj.Transformer` /
`shapely.ops.transform` pipeline, since geopandas already gets this right.
"""

import geopandas as gpd
from pyproj import CRS
from shapely.geometry.base import BaseGeometry


def estimate_metric_crs(geometry: BaseGeometry, crs: CRS) -> CRS:
    """Estimates a projected (metric) CRS appropriate for `geometry`, e.g. its UTM zone."""
    series = gpd.GeoSeries([geometry], crs=crs)
    return series.estimate_utm_crs()


def reproject(geometry: BaseGeometry, src_crs: CRS, dst_crs: CRS) -> BaseGeometry:
    """Reprojects a single geometry from `src_crs` to `dst_crs`."""
    series = gpd.GeoSeries([geometry], crs=src_crs)
    return series.to_crs(dst_crs).iloc[0]
