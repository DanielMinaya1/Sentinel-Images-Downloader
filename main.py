from utils import get_keycloak, process_dates, download_data
from dotenv import load_dotenv
import argparse
import os

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-ti', '--tile_ids', 
        help="Ids of the tiles to download", 
        required=False, type=str, nargs='+', 
        default=['T19HCC']
    )
    parser.add_argument(
        '-id', '--initial_date', 
        help="Start date to download", 
        required=False, type=str, 
        default="2018-01-01"
    )
    parser.add_argument(
        '-ld', '--last_date', 
        help="End date to download", 
        required=False, type=str, 
        default="2023-12-31"
    )
    parser.add_argument(
        '-b', '--bands', 
        help="Bands to download",
        required=False, type=str, nargs='+', 
        default=[
            'B02_10m', 'B03_10m', 'B04_10m', 'B08_10m', 
            'B05_20m', 'B06_20m', 'B07_20m', 'B8A_20m',
            'B11_20m', 'B12_20m', 'SCL_20m', 'TCI_10m'
        ]
    )
    parser.add_argument(
        '-od', '--output_directory', 
        help="Path to save the files", 
        required=False, type=str, 
        default="D:/Sentinel-2"
    )
    parser.add_argument(
        '-i', '--iters', 
        help="Number of iterations", 
        required=False, type=int,
        default=1
    )

    args = parser.parse_args()
    load_dotenv()

    username = os.getenv("COPERNICUS_USERNAME")
    password = os.getenv("COPERNICUS_PASSWORD")
    access_token = get_keycloak(username, password)
    
    date_ranges = process_dates(args.initial_date, args.last_date)

    for _ in range(args.iters):
        for date_range in date_ranges:
            for tile_id in args.tile_ids:
                download_data(
                    tile_id, *date_range, 
                    'L2A', args.output_directory, 
                    access_token, args.bands
                )
            access_token = get_keycloak(username, password)
