# TODO

Next up: geometry-focused features. Given an arbitrary polygon, line, or point (an AOI), work with the Sentinel-2 imagery already downloaded locally around it, rather than just downloading whole tiles.

## 1. Tile matching for a geometry
Given a polygon/line/point, determine which Sentinel-2 tile(s) it intersects, and which single tile covers it best (fully contains it, or has the largest overlap) — needed whenever an AOI sits near or straddles a tile boundary.

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
- **Flexible AOI input** — accept GeoJSON/WKT/shapefile as input instead of a hardcoded polygon format, so other geometries can be plugged in easily.
- **Exportable time series** — CSV/GeoDataFrame/Parquet output from #3, so results plug into pandas/QGIS/etc. instead of being locked into this tool.
- **Quick visualization helpers** — a one-liner to preview an AOI over a cropped image (matplotlib), useful once #4 exists, especially in notebooks.
- **STAC support** — Copernicus Dataspace exposes a STAC API; querying through it instead of raw OData would make this interoperable with the broader EO tooling ecosystem (`pystac-client`, `odc-stac`, etc.).
