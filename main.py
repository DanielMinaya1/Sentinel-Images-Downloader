from downloader.s2_downloader import Sentinel2
from downloader.utils import load_json
from dotenv import load_dotenv
from pathlib import Path
import argparse
import os

SATELLITE_DOWNLOADERS = {
    "s2": Sentinel2
}

def main():
    parser = argparse.ArgumentParser()  
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

    config_name = args.config_name or f"{args.satellite}_default_config.json"
    config_path = Path(f"config/{config_name}")
    config = load_json(config_path)

    username = os.getenv("COPERNICUS_USERNAME")
    password = os.getenv("COPERNICUS_PASSWORD")

    DownloaderClass = SATELLITE_DOWNLOADERS[args.satellite]
    downloader = DownloaderClass(username, password, **config)

    downloader.download()

if __name__ == "__main__":
    main()