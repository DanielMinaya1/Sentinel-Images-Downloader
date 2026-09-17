# Sentinel Images Downloader

A Python script to download Sentinel-1 and Sentinel-2 images from the Copernicus Browser. Supports specifying footprints or tile IDs, date range, and relevant parameters such as polarization, orbit direction, and bands for retrieval.

## Requirements
1. Copernicus Data Space Account: Register for a free account on the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/).
2. Credentials Setup: Create a .env file in the project directory with your login.
```text 
COPERNICUS_USERNAME=your_username
COPERNICUS_PASSWORD=your_password
```

## Installation
**1. Clone the Repository**
```bash
git clone https://github.com/DanielMinaya1/sentinel-images-downloader.git
cd sentinel-images-downloader
```
**2. Install Dependencies**

This project uses [Poetry](https://python-poetry.org/) to manage its virtual environment and dependencies:
```bash
poetry install
```

## Usage
### Basic Usage
Run the script with the default settings:
```bash
poetry run python -m downloader.main
```
This will download **Sentinel-2** images using the default configuration:
* **Tile ID**: T19HCC
* **Dates**: 2018-2023
* **Bands**: All 10m and 20m resolution bands, plus ```SCL_20m``` and ```TCI_10m```

The default parameters are loaded from the file ```s2_default_config.json```.

To download **Sentinel-1** images instead, run:
```bash
poetry run python -m downloader.main -s s1
```

This will use the default Sentinel-1 configuration:
* **Database Path**: ```data/sentinel.db```
* **Dates**: 2018-2023
* **Product Type**: GRD
* **Polarization**: VV, VH
* **Orbit Direction**: DESCENDING

The default parameters are loaded from the file ```s1_default_config.json```.

### Custom Parameters
You can customize the download by creating a new configuration file, typically in the ```examples/``` directory. The file should follow the format below, depending on whether you are downloading Sentinel-1 or Sentinel-2 data.

#### Sentinel-1 Configuration
| Entry | Description | Default Value |
| -------- | ----------- | ------------- |
| ```db_path```  | Path to the SQLite database containing the `s1_footprints` table (tile_id -> AOI polygon) | ```data/sentinel.db``` |
| ```initial_date``` | Start date of the data | ```2018-01-01``` |
| ```last_date``` | End date of the data | ```2023-12-31``` |
| ```product_type``` | Type of Sentinel-1 product (e.g., "GRD", "SLC")  | ```GRD``` |
| ```polarization_mode``` | List of polarization modes to download (e.g., "VV", "VH", "HH", "HV") | ```['VV', 'VH']``` |
| ```orbit_direction``` | Orbit direction of Sentinel-1 (e.g., "ASCENDING", "DESCENDING") | ```DESCENDING``` |
| ```output_dir``` | Directory where the files will be saved | Current working directory |
| ```max_retries``` | Number of retries to download a file | ```3``` |

#### Sentinel-2 Configuration
| Entry | Description | Default Value |
| -------- | ----------- | ------------- |
| ```tile_ids```  | List of tile IDs to download | ```['T19HCC']``` |
| ```initial_date``` | Start date of the data | ```2018-01-01``` |
| ```last_date``` | End date of the data | ```2023-12-31``` |
| ```band_selection``` | List of bands to download | ```['B02_10m', 'B03_10m','B04_10m', 'B08_10m', 'B05_20m', 'B06_20m', 'B07_20m', 'B8A_20m', 'B11_20m', 'B12_20m', 'SCL_20m', 'TCI_10m']``` |
| ```product_level``` | Product level of S2 (can be "L1C" or "L2A") | ```L2A``` |
| ```db_path``` | Path to the SQLite database containing the `s2_orbits` table (tile_id -> relative orbit) | ```data/sentinel.db``` |
| ```output_dir``` | Directory where the files will be saved | Current working directory |
| ```max_retries``` | Number of retries to download a file | ```3``` |

To use a custom configuration, specify the file name when running the script. It's looked up in the ```examples/``` directory first, then as a literal path:
```bash
poetry run python -m downloader.main -s s1 -c my_custom_s1_config.json
```
or 
```bash
poetry run python -m downloader.main -s s2 -c my_custom_s2_config.json
```

### Reference Data (`data/sentinel.db`)
Sentinel-1 AOI footprints and Sentinel-2 relative orbits are looked up from a small SQLite database, ```data/sentinel.db```, referenced by the ```db_path``` config entry. To add or update a tile, use the repository classes directly instead of hand-editing a file:
```python
from downloader.storage.repositories import FootprintRepository, OrbitRepository

FootprintRepository("data/sentinel.db").upsert(
    "T19KCP", ["-69.9 -34.4", "-69.9 -35.4", "-68.8 -35.4", "-68.8 -34.4", "-69.9 -34.4"],
)
OrbitRepository("data/sentinel.db").upsert("T19KCP", "R139")
```

### Downloading a Single Tile
To download just one tile/footprint instead of everything in the config, pass ```-t```/```--tile```:
```bash
poetry run python -m downloader.main -s s2 -t T19KCP
```

### Programmatic Usage
For use from other Python code (e.g. a notebook or another script) without going through the CLI, `downloader.api` exposes the same functionality directly:
```python
from downloader.api import download_tile

summary = download_tile("s2", "T19KCP")
print(f"{summary.succeeded} succeeded, {summary.failed} failed, {summary.skipped} skipped")
```
With no `config` argument, it uses the satellite's default example config (falling back to `COPERNICUS_USERNAME`/`COPERNICUS_PASSWORD` from the environment or a `.env` file for credentials, same as the CLI). Pass `config=` (a dict or a `Sentinel1Config`/`Sentinel2Config`) and/or `username`/`password` to override either.

### Example Command
To download Sentinel-2 images for tile T19KCP from 2019 to 2022, including specific bands, create:
```json
{
    "tile_ids": ["T19KCP"],
    "band_selection": ["B02_10m", "B8A_20m", "TCI_10m"],
    "initial_date": "2019-01-01",
    "last_date": "2022-12-31", 
    "product_level": "L2A",
    "db_path": "data/sentinel.db",
    "output_dir": "/path/to/output",
    "max_retries": 3
}
```
and run
```bash
poetry run python -m downloader.main -c config.json
```

### Download Summary
At the end of a run (CLI or programmatic), a summary report is logged showing per-tile and per-product counts of succeeded/failed/skipped files, including the specific files that failed and why:
```text
=== Download Summary ===
Tiles: 1  Succeeded: 11  Failed: 1  Skipped: 0

Tile T19HCC: 2 product(s) - 11 succeeded, 1 failed, 0 skipped
  - S2A_MSIL2A_20230115.SAFE [SUCCESS]: 6 succeeded, 0 failed, 0 skipped
  - S2A_MSIL2A_20230201.SAFE [FAILED]: 5 succeeded, 1 failed, 0 skipped
      FAILED: Sentinel-2/S2A_MSIL2A_20230201.SAFE/.../B04_10m.jp2 - HTTP 500
```

### Output Structure
The downloaded files will be saved as .SAFE folder in the specified ```output_dir``` with the following structure:

#### Sentinel-2 Output Structure
```text
output_directory/
├── <product_name>.SAFE/
    ├── manifest.safe
    ├── GRANULE/
        ├── <granule_name>/
            ├── IMG_DATA/
                ├── R10m/
                    ├── B02_10m.jp2
                    ├── ...
                ├── R20m/
                    ├── B05_20m.jp2
                    ├── ...
```
#### Sentinel-1 Output Structure
```text
output_directory/
├── <product_name>.SAFE/
    ├── manifest.safe
    ├── measurement/
        ├── s1a-iw-grd-vh-<date>.tiff
        ├── s1a-iw-grd-vv-<date>.tiff
    ├── annotation/
        ├── calibration/
            ├── calibration-s1b-iw-grd-vh-<date>.xml
            ├── calibration-s1b-iw-grd-vv-<date>.xml
            ├── noise-s1b-iw-grd-vh-<date>.xml
            ├── noise-s1b-iw-grd-vv-<date>.xml
        ├── s1a-iw-grd-vh-<date>.xml
        ├── s1a-iw-grd-vv-<date>.xml
```
Each product contains only the polarization modes specified during the download.