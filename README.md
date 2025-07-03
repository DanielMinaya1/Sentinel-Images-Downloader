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
**2. Create a Virtual Environment**
```bash
python -m venv venv
venv\scripts\activate
```

**3. Install Dependencies**

Install all the necessary dependencies using:
```bash
pip install -e .
```

## Usage
### Basic Usage
Run the script with the default settings:
```bat 
python -m sentinel_images_downloader.main
```
This will download **Sentinel-2** images using the default configuration:
* **Tile ID**: T19HCC
* **Dates**: 2018-2023
* **Bands**: All 10m and 20m resolution bands, plus ```SCL_20m``` and ```TCI_10m```

The default parameters are loaded from the file ```s2_default_config.json```.

To download **Sentinel-1** images instead, run:
```bat 
python -m sentinel_images_downloader.main -s s1
```

This will use the default Sentinel-1 configuration:
* **Footprints Path**: ```data/s1_footprints.json```
* **Dates**: 2018-2023
* **Product Type**: GRD
* **Polarization**: VV, VH
* **Orbit Direction**: DESCENDING

The default parameters are loaded from the file ```s1_default_config.json```.

### Custom Parameters
You can customize the download by creating a new configuration file in the config directory. The file should follow the format below, depending on whether you are downloading Sentinel-1 or Sentinel-2 data.

#### Sentinel-1 Configuration
| Entry | Description | Default Value |
| -------- | ----------- | ------------- |
| ```footprints_path```  | Path to a GeoJSON file defining the AOIs | ```data/s1_footprints.json``` |
| ```initial_date``` | Start date of the data | ```2018-01-01``` |
| ```last_date``` | End date of the data | ```2023-12-31``` |
| ```product_type``` | Type of Sentinel-1 product (e.g., "GRD", "SLC")  | ```GRD``` |
| ```polarization_mode``` | List of polarization modes to download (e.g., "VV", "VH", "HH", "HV") | ```L2A``` |
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
| ```relative_orbits_path``` | Path to a JSON file containing orbit information for the specified tiles | ```data/s2_relative_orbits.json``` |
| ```output_dir``` | Directory where the files will be saved | Current working directory |
| ```max_retries``` | Number of retries to download a file | ```3``` |

To use a custom configuration, specify the file name when running the script:
```bat 
python -m sentinel_images_downloader.main -s s1 -c my_custom_s1_config.json
```
or 
```bat 
python -m sentinel_images_downloader.main -s s2 -c my_custom_s2_config.json
```
### Example Command
To download Sentinel-2 images for tile T19KCP from 2019 to 2022, including specific bands, create:
```json
{
    "tile_ids": ["T19KCP"],
    "band_selection": ["B02_10m", "B8A_20m", "TCI_10m"],
    "initial_date": "2019-01-01",
    "last_date": "2022-12-31", 
    "product_level": "L2A",
    "relative_orbits_path": "data/s2_orbits.json",
    "output_dir": "/path/to/output",
    "max_retries": 3
}
```
and run
```bat 
python -m sentinel_images_downloader.main -c config.json
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