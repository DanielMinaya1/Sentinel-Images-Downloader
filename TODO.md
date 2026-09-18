# TODO

Next up: geometry-focused features. Given an arbitrary polygon, line, or point (an AOI), work with the Sentinel-2 imagery already downloaded locally around it, rather than just downloading whole tiles.

## 0. Flexible AOI input — done
`downloader.geometry.AOI` accepts GeoJSON, WKT, a raw shapely geometry, a GeoDataFrame/GeoSeries, or PostGIS (`AOI.from_postgis(sql, con)`, caller supplies the connection). Internally it's a shapely geometry + explicit CRS; `kind` (`POINT`/`LINE`/`POLYGON`) is derived from the geometry, folding Multi* variants into the same kind as their single counterpart. `aoi.to_polygon(buffer_meters=..., crs=...)` is the one method #1-#5 below will call — it reprojects to a metric CRS before buffering (never buffers raw degrees) and requires a buffer for POINT/LINE kinds since they have no area of their own. See `downloader/geometry/aoi.py` and `tests/test_geometry_aoi.py`.

## 1. Tile matching for a geometry — done
`downloader.tiles.match_tiles(aoi, db_path=...)` returns every Sentinel-2 tile intersecting an AOI, sorted best-first (`TileMatch.overlap_fraction`, `.contains`). Checks the `s2_tile_footprints` cache (a third table in `data/sentinel.db`) first; on a miss, queries the Copernicus catalogue's `OData.CSC.Intersects` against the AOI's bounding box (`downloader.tiles.discovery`, unauthenticated) and caches every distinct tile it discovers for next time — verified live: a fresh area takes ~15s (one network round trip), a cached one ~0.05s. Ranking reprojects into a metric CRS first (reusing the Phase-0 CRS helpers) and uses area-overlap for POLYGON, length-overlap for LINE, intersects-or-not for POINT. See `downloader/tiles/` and `tests/test_tiles.py`.

## 2. Cloud filtering scoped to the AOI, not the tile
Copernicus's cloud-cover filter is tile-wide, which doesn't work for small AOIs: a tile can pass the filter while the clouds sit right over the AOI, or fail it while the AOI itself (or the area around a line/point) is clear. Need per-pixel cloud detection (e.g. from the SCL band) clipped to the geometry (plus a buffer for lines/points) to get an AOI-specific cloud percentage instead of the tile-wide one.

## 3. Time series per band / index
Given a polygon and a folder of already-downloaded local images, build a time series of band values — or a derived index from multiple bands, like NDVI — over the available dates for that AOI.

## 4. Crop an image to a geometry + buffer
Crop a single date's image to a polygon, line, or point with a buffer. Start with the TCI_10m layer. This is a building block for both #3 (time series) and #5 (best image).

## 5. Best cloud-free image near a target date (end goal)
Given a polygon and a target date, return the nearest-date Sentinel-2 TCI image that isn't too cloudy *specifically over that polygon*. Combines #1 (find the tile), #2 (AOI-scoped cloud check across candidate dates), and #4 (crop to the AOI).

---

Likely needs: a geometry library (e.g. shapely/geopandas) for intersection/containment/buffering and CRS handling between AOI coordinates (usually WGS84) and tile UTM grids — `rasterio` is already a dependency and covers the clipping/windowed-read side.

## Lower priority

Not needed for the AOI visualization goal above, but worth revisiting later.

- **S1 fallback for #5** — SAR is immune to clouds. If no clean-enough S2 image exists near the target date, fall back to the nearest S1 acquisition instead of just relaxing the cloud threshold.
- **Exportable time series** — CSV/GeoDataFrame/Parquet output from #3, so results plug into pandas/QGIS/etc. instead of being locked into this tool.
- **Quick visualization helpers** — a one-liner to preview an AOI over a cropped image (matplotlib), useful once #4 exists, especially in notebooks.
- **STAC support** — Copernicus Dataspace exposes a STAC API; querying through it instead of raw OData would make this interoperable with the broader EO tooling ecosystem (`pystac-client`, `odc-stac`, etc.).
