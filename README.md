# Sentinel Images Downloader

A Python script to download Sentinel-2 images from Copernicus Browser, specifying tile IDs, date range, and bands for retrieval.

## Requirements
1. Copernicus Data Space Account: Register for a free account on the [Copernicus Data Space Ecosystem](https://dataspace.copernicus.eu/).
2. Credentials Setup: Create a .env file in the project directory with your login.
```text 
COPERNICUS_USERNAME=your_username
COPERNICUS_PASSWORD=your_password
```

## Usage
### Basic Usage
Run the script with the default settings:
```bat 
python main.py
```
This will download Sentinel-2 images using the default configuration:
* **Tile ID**: T19HCC,
* **Dates**: 2018-2023,
* **Bands**: All 10m and 20m resolution bands, plus ```SCL_20m``` and ```TCI_10m```.

The default parameters are loaded from the file ```s2_default_config.json```.

### Custom Parameters
You can customize the download by creating a new file ```config.json``` in the ```config``` directory with the followings entries:
| Entry | Description | Default Value |
| -------- | ----------- | ------------- |
| ```tile_ids```  | List of tile IDs to download | ```['T19HCC']``` |
| ```initial_date``` | Start date of the data | ```2018-01-01``` |
| ```last_date``` | End date of the data | ```2023-12-31``` |
| ```bands``` | List of bands to download | ```['B02_10m', 'B03_10m','B04_10m', 'B08_10m', 'B05_20m', 'B06_20m', 'B07_20m', 'B8A_20m', 'B11_20m', 'B12_20m', 'SCL_20m', 'TCI_10m']``` |
| ```product_level``` | Product level of S2 (can be "L1C" or "L2A") | ```L2A``` |
| ```orbit_path``` | Path to a JSON file containing orbit information for the specified tiles | ```data/s2_orbits.json``` |
| ```output_dir``` | Directory where the files will be saved | Current working directory |

### Example command
To download images for tile T19KCP from 2019 to 2022, including specific bands, create:
```json
{
    "tile_ids": ["T19KCP"],
    "bands": ["B02_10m", "B8A_20m", "TCI_10m"],
    "initial_date": "2019-01-01",
    "last_date": "2022-12-31", 
    "product_level": "L2A",
    "orbit_path": "data/s2_orbits.json",
    "output_dir": "/path/to/output"
}
```
and run
```bat 
python main.py -cn config.json
```

### Output structure
The downloaded files will be saved as .SAFE folders in the specified output_directory with the following structure:
```text
output_directory/
├── T19HCC/
    ├── <product_name>.SAFE/
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
Each product contains only the bands specified during the download.