"""
Public, importable entry point for triggering a Sentinel download from other
Python code, without going through the CLI/argparse flow in `downloader.main`.

Example:
    from downloader.api import download_tile
    summary = download_tile("s2", "T19HCC")
    print(f"{summary.succeeded} succeeded, {summary.failed} failed")
"""

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, TypeAlias

from dotenv import load_dotenv

from downloader.downloaders import Sentinel1, Sentinel2
from downloader.downloaders.base_downloader import SentinelDownloader
from downloader.models import (
    Sentinel1Config,
    Sentinel2Config,
    SentinelConfig,
    TileDownloadSummary,
)
from downloader.utils.io import load_json, resolve_config_path

Satellite = Literal["s1", "s2"]

# Mapping of satellite names to their respective downloader/config classes.
SATELLITE_DOWNLOADERS: dict[str, type[SentinelDownloader]] = {"s1": Sentinel1, "s2": Sentinel2}
SATELLITE_CONFIGS: dict[str, type[SentinelConfig]] = {"s1": Sentinel1Config, "s2": Sentinel2Config}

ConfigLike: TypeAlias = dict[str, Any] | SentinelConfig


def _resolve_credentials(
    username: str | None,
    password: str | None,
) -> tuple[str, str]:
    load_dotenv()
    username = username or os.getenv("COPERNICUS_USERNAME")
    password = password or os.getenv("COPERNICUS_PASSWORD")

    if not username or not password:
        raise ValueError(
            "Copernicus credentials not provided. Pass username/password "
            "explicitly, or set COPERNICUS_USERNAME/COPERNICUS_PASSWORD "
            "(e.g. in a .env file)."
        )
    return username, password


def _resolve_config(
    satellite: Satellite,
    config: ConfigLike | None,
) -> SentinelConfig:
    if isinstance(config, SentinelConfig):
        return config

    config_dict: dict[str, Any] = (
        config
        if config is not None
        else load_json(
            resolve_config_path(f"{satellite}_default_config.json"),
        )
    )
    ConfigClass = SATELLITE_CONFIGS[satellite]
    return ConfigClass.from_json(config_dict)


def build_downloader(
    satellite: Satellite,
    config: ConfigLike | None = None,
    *,
    username: str | None = None,
    password: str | None = None,
) -> SentinelDownloader:
    """
    Builds a ready-to-use `Sentinel1`/`Sentinel2` instance.

    `config` may be a `Sentinel1Config`/`Sentinel2Config`, a plain dict shaped
    like one of the example config JSON files, or omitted entirely to fall
    back to the satellite's default example config.
    """
    username, password = _resolve_credentials(username, password)
    resolved_config = _resolve_config(satellite, config)

    DownloaderClass = SATELLITE_DOWNLOADERS[satellite]
    return DownloaderClass(
        username=username,
        password=password,
        **resolved_config.to_kwargs(),
    )


def download_tile(
    satellite: Satellite,
    tile_id: str,
    *,
    username: str | None = None,
    password: str | None = None,
    config: ConfigLike | None = None,
    output_dir: str | Path | None = None,
) -> TileDownloadSummary:
    """
    Downloads every available product for a single tile/footprint and
    returns a `TileDownloadSummary` of what happened - no CLI or config
    file required.

    Args:
        satellite: "s1" or "s2".
        tile_id: The Sentinel-1 footprint id or Sentinel-2 tile id to
                 download, as stored in `data/sentinel.db`.
        username, password: Copernicus credentials. Fall back to the
                 COPERNICUS_USERNAME/COPERNICUS_PASSWORD env vars (or a
                 .env file) when omitted.
        config: A `Sentinel1Config`/`Sentinel2Config`, an equivalent dict,
                or omitted to use the satellite's default example config.
        output_dir: Overrides the config's output directory when given.
    """
    resolved_config = _resolve_config(satellite, config)

    if output_dir is not None:
        resolved_config = replace(resolved_config, output_dir=str(output_dir))

    if isinstance(resolved_config, Sentinel2Config) and not resolved_config.tile_ids:
        resolved_config = replace(resolved_config, tile_ids=[tile_id])

    downloader = build_downloader(
        satellite,
        resolved_config,
        username=username,
        password=password,
    )
    return downloader.download_tile(tile_id)
