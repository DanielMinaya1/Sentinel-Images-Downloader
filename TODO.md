# TODO

Next up: geometry-focused features. Given an arbitrary polygon, line, or point (an AOI), work with the Sentinel-2 imagery already downloaded locally around it, rather than just downloading whole tiles.

## 0. Flexible AOI input — done
`downloader.geometry.AOI` accepts GeoJSON, WKT, a raw shapely geometry, a GeoDataFrame/GeoSeries, or PostGIS (`AOI.from_postgis(sql, con)`, caller supplies the connection). Internally it's a shapely geometry + explicit CRS; `kind` (`POINT`/`LINE`/`POLYGON`) is derived from the geometry, folding Multi* variants into the same kind as their single counterpart. `aoi.to_polygon(buffer_meters=..., crs=...)` is the one method #1-#5 below will call — it reprojects to a metric CRS before buffering (never buffers raw degrees) and requires a buffer for POINT/LINE kinds since they have no area of their own. See `downloader/geometry/aoi.py` and `tests/test_geometry_aoi.py`.

## 1. Tile matching for a geometry — done
`downloader.tiles.match_tiles(aoi, db_path=...)` returns every Sentinel-2 tile intersecting an AOI, sorted best-first (`TileMatch.overlap_fraction`, `.contains`). Checks the `s2_tile_footprints` cache (a third table in `data/sentinel.db`) first; on a miss, queries the Copernicus catalogue's `OData.CSC.Intersects` against the AOI's bounding box (`downloader.tiles.discovery`, unauthenticated) and caches every distinct tile it discovers for next time — verified live: a fresh area takes ~15s (one network round trip), a cached one ~0.05s. Ranking reprojects into a metric CRS first (reusing the Phase-0 CRS helpers) and uses area-overlap for POLYGON, length-overlap for LINE, intersects-or-not for POINT. See `downloader/tiles/` and `tests/test_tiles.py`.

## 2. Cloud filtering scoped to the AOI, not the tile — done
`downloader.clouds.compute_cloud_fraction(scl_path, aoi, buffer_meters=..., cloud_classes=...)` reads a downloaded product's local SCL band (found via `find_scl_band(product_dir)`, matching the SAFE layout the downloader already produces) and returns a `CloudStats` (`cloud_fraction`, `cloud_pixels`, `valid_pixels`, `total_pixels`) scoped to the AOI's actual pixels, not the tile-wide metadata. Uses `aoi.to_polygon()` from #0 to get the buffered polygon in the raster's own CRS, then `rasterio.mask.mask()` to clip. Default cloud classes: `{3, 8, 9, 10}` (cloud shadow, cloud medium/high probability, thin cirrus), overridable. Caveat worth knowing: a `buffer_meters` much smaller than SCL's 20m resolution can miss every pixel center — check `valid_pixels` if the result covers only one or two pixels. See `downloader/clouds.py` and `tests/test_clouds.py`.

## 3. Time series per band / index
Given a polygon and a folder of already-downloaded local images, build a time series of band values — or a derived index from multiple bands, like NDVI — over the available dates for that AOI.

## 4. Crop an image to a geometry + buffer — done (tackled before #3, which depends on it)
`downloader.rasters.crop_image(image_path, aoi, buffer_meters=..., output_path=...)` crops any single- or multi-band raster (starting with TCI_10m) to an AOI's (buffered) polygon, returning a `CroppedImage` (`data`, `transform`, `crs`, `output_path`); writes a GeoTIFF to `output_path` if given, regardless of the input's own format (JP2 write support isn't reliably available across GDAL builds the way read is, GeoTIFF write is universal). Built on a new shared primitive, `clip_raster()`, which `downloader.clouds.compute_cloud_fraction` (#2) was refactored to reuse instead of duplicating the same open/`to_polygon`/`mask` steps. See `downloader/rasters.py` and `tests/test_rasters.py`.

## 4b. Visualize an AOI over an image (JPG export) — done
`downloader.visualization.create_aoi_image(image_path, aoi, output_path, buffer_meters=...)` crops an image (via `crop_image` from #4), draws the AOI's boundary on top, and saves it as a JPG (or any matplotlib-supported format) — this is the actual visual output the AOI-visualization goal was for. Lower-level pieces (`render_aoi_image`, `save_figure`) are exposed separately for further customization before saving. Adapted from a working matplotlib+geopandas pattern the user had in an old repo. See `downloader/visualization.py` and `tests/test_visualization.py`.

## 5. Best cloud-free image near a target date (end goal) — done
`downloader.best_image.find_best_image(aoi, target_date, ...)` returns a `BestImageResult` (`product`, `tile_id`, `cloud_stats`, `image_path`). Combines #1 (`match_tiles` to find the tile), #2 (AOI-scoped cloud check), and #4/#4b (crop + save the winning image): searches candidate dates within `search_window_days` (default 15) of `target_date`, nearest first, downloading only the cheap SCL band per candidate to check its AOI cloud fraction (`downloader.clouds.compute_cloud_fraction`) - never a full band set for a rejected candidate - and stops at the first one at or under `max_cloud_fraction` (default 20%). Only then downloads TCI_10m for the winner and saves the AOI-boundary JPG. Raises `NoCleanImageFoundError` (naming how many were checked and the best fraction found) if nothing in the window qualifies. Along the way, fixed a real bug in `match_tiles` (#1): its cache check compared a non-WGS84 AOI's raw coordinates against WGS84-stored footprints without reprojecting first, which could silently miss real cache hits for e.g. a PostGIS AOI in a projected CRS. See `downloader/best_image.py`, `tests/test_best_image.py`, and the added regression test in `tests/test_tiles.py`. Also added `find_best_image_in_range(geometry, start_date, end_date, output_dir)`, the caller-facing variant: takes a GeoJSON dict or `AOI` and a date range, picks the lowest-cloud date (cloud-free by default), saves only the JPG to `output_dir` (raw downloads go to a temp dir), and returns `None` instead of raising when nothing qualifies.

---

Likely needs: a geometry library (e.g. shapely/geopandas) for intersection/containment/buffering and CRS handling between AOI coordinates (usually WGS84) and tile UTM grids — `rasterio` is already a dependency and covers the clipping/windowed-read side.

## Lower priority

Not needed for the AOI visualization goal above, but worth revisiting later.

- **S1 fallback for #5** — SAR is immune to clouds. If no clean-enough S2 image exists near the target date, fall back to the nearest S1 acquisition instead of just relaxing the cloud threshold.
- **Exportable time series** — CSV/GeoDataFrame/Parquet output from #3, so results plug into pandas/QGIS/etc. instead of being locked into this tool.
- **STAC support** — Copernicus Dataspace exposes a STAC API; querying through it instead of raw OData would make this interoperable with the broader EO tooling ecosystem (`pystac-client`, `odc-stac`, etc.).
