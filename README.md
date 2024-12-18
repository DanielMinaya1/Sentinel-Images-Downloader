# Sentinel Images Downloader

A Python script to download Sentinel-2 images from Copernicus Browser, specifying tile IDs, years, and bands for retrieval.

## Requirements
1. Copernicus Account: Register for a free account on Copernicus.
2. Credentials Setup: Create a .env file in the project directory with your login 
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
This downloads Sentinel-2 images for:
* **Tile ID**: T19HCC,
* **Years**: 2018-2023,
* **Bands**: All 10m and 20m resolution bands, plus ```SCL_20m``` and ```TCI_10m```.

### Custom Parameters
You can customize the download using the following parameters:
| Flag     | Description | Default Value |
| -------- | ----------- | ------------- |
| ```-ti --tile_ids```  | List of tile IDs to download | ```['T19HCC']``` |
| ```-iy --initial_year``` | Start year of the data | ```2018``` |
| ```-ey --end_year``` | End year of the data | ```2023``` |
| ```-b --bands``` | List of bands to download | ```['B02_10m', 'B03_10m','B04_10m', 'B08_10m', 'B05_20m', 'B06_20m', 'B07_20m', 'B8A_20m', 'B11_20m', 'B12_20m', 'SCL_20m', 'TCI_10m'']``` |
| ```-od --output_directory``` | Directory where the files will be saved | Current working directory |
| ```-i --iters``` | Number of iterations | ```1``` |

### Example command
To download images for tile T19KCP from 2019 to 2022, including specific bands, use:
```bat 
python main.py -ti T19HCC -iy 2019 -ly 2022 -b B02_10m B08_10m TCI_10m -od /path/to/output
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