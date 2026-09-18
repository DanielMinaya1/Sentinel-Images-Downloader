"""
CLI entry point for downloading Sentinel satellite data.

This is a thin wrapper around `downloader.api`: it parses arguments, loads
the corresponding configuration, and either downloads a single tile or runs
the full configured download. See `downloader.api` for the equivalent
programmatic (importable) interface.
"""

import argparse
from datetime import datetime

from downloader.api import SATELLITE_DOWNLOADERS, build_downloader
from downloader.config.logger import setup_logger
from downloader.config.path import LOGS_DIR
from downloader.reporting import format_run_report, format_tile_report
from downloader.utils.io import load_json, resolve_config_path

today = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
log_path = LOGS_DIR / f"{today}.log"
logger = setup_logger(file_name=log_path)


def main():
    """
    Parses command-line arguments, loads the appropriate configuration,
    and initializes the downloader.

    Retrieves API credentials from environment variables and starts the
    data download for the specified satellite.
    """
    parser = argparse.ArgumentParser(description="Sentinel Satellite Data Downloader")
    parser.add_argument(
        "-s",
        "--satellite",
        help="Name of the satellite to use as data source",
        required=False,
        type=str,
        default="s2",
        choices=SATELLITE_DOWNLOADERS.keys(),
    )
    parser.add_argument(
        "-c",
        "--config_path",
        help="Name of the config.json to customize the download.",
        required=False,
        type=str,
        default=None,
    )
    parser.add_argument(
        "-t",
        "--tile",
        help="Download a single tile/footprint id instead of the full config.",
        required=False,
        type=str,
        default=None,
    )

    args = parser.parse_args()

    # Determine config file name (use default if not provided)
    config_path = args.config_path or f"{args.satellite}_default_config.json"
    config_path = resolve_config_path(config_path)
    config = load_json(config_path)

    downloader = build_downloader(args.satellite, config)

    if args.tile:
        summary = downloader.download_tile(args.tile)
        logger.info("Downloading complete.\n" + format_tile_report(summary))
    else:
        run_summary = downloader.download()
        logger.info("Downloading complete.\n" + format_run_report(run_summary))


if __name__ == "__main__":
    main()
