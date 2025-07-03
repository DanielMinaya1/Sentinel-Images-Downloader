"""
Module for downloading Sentinel satellite data.

This script initializes a downloader for Sentinel-1 or Sentinel-2 based on user input
and loads the corresponding configuration. It retrieves authentication credentials
from environment variables and starts the download process.
"""

from sentinel_images_downloader.downloader.s1_downloader import Sentinel1
from sentinel_images_downloader.downloader.s2_downloader import Sentinel2
from sentinel_images_downloader.downloader.utils import load_json
from sentinel_images_downloader.config.path import LOGS_DIR
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import argparse
import os

from sentinel_images_downloader.config.logger import setup_logger
today = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
log_path = LOGS_DIR / f"{today}.log"
logger = setup_logger(file_name=log_path)

# Mapping of satellite names to their respective downloader classes
SATELLITE_DOWNLOADERS = {
    "s1": Sentinel1,
    "s2": Sentinel2
}

def main():
    """
    Parses command-line arguments, loads the appropriate configuration, 
    and initializes the downloader.

    Retrieves API credentials from environment variables and starts the 
    data download for the specified satellite.
    """
    parser = argparse.ArgumentParser(description="Sentinel Satellite Data Downloader")  
    parser.add_argument(
        "-s", "--satellite",
        help="Name of the satellite to use as data source",
        required=False, type=str,
        default="s2",
        choices=SATELLITE_DOWNLOADERS.keys()
    )
    parser.add_argument(
        "-c", "--config_name",
        help="Name of the config.json to customize the download.",
        required=False, type=str,
        default=None
    )

    args = parser.parse_args()
    load_dotenv()

    # Determine config file name (use default if not provided)
    config_name = args.config_name or f"{args.satellite}_default_config.json"
    config_path = Path(f"config/{config_name}")
    config = load_json(config_path)

    # Retrieve authentication credentials
    username = os.getenv("COPERNICUS_USERNAME")
    password = os.getenv("COPERNICUS_PASSWORD")

    # Initialize and start the downloader
    DownloaderClass = SATELLITE_DOWNLOADERS[args.satellite]
    downloader = DownloaderClass(username, password, **config)
    downloader.download()
    logger.info("Downloading complete...")

if __name__ == "__main__":
    main()