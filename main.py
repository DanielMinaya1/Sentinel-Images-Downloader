from downloader.downloader import Sentinel2
from downloader.utils import load_json
from dotenv import load_dotenv
from pathlib import Path
import argparse
import os

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-cn", "--config_name",
        help="Name of the config.json to customize the download.",
        required=False, type=str,
        default="s2_default_config.json"
    )

    args = parser.parse_args()
    load_dotenv()

    config_path = Path(f"config/{args.config_name}")
    config = load_json(config_path)

    username = os.getenv("COPERNICUS_USERNAME")
    password = os.getenv("COPERNICUS_PASSWORD")

    downloader = Sentinel2(
        username, password,
        config["tile_ids"], config["product_level"], config["orbit_path"],
        config["initial_date"], config["last_date"],
        config["bands"], config["output_dir"]
    )
    downloader.download()