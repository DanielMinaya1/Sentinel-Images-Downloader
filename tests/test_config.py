import pytest

from downloader.models import Sentinel1Config, Sentinel2Config

S1_DATA = {
    "initial_date": "2018-01-01",
    "last_date": "2018-01-31",
    "output_dir": "Sentinel-1",
    "max_retries": 3,
    "db_path": "data/sentinel.db",
    "orbit_direction": "DESCENDING",
    "product_type": "GRD",
    "polarization_mode": ["VV", "VH"],
}

S2_DATA = {
    "initial_date": "2018-01-01",
    "last_date": "2018-01-11",
    "output_dir": "Sentinel-2",
    "max_retries": 3,
    "tile_ids": ["T19HCC"],
    "product_level": "L2A",
    "db_path": "data/sentinel.db",
    "band_selection": ["B02_10m"],
}


def test_sentinel1_config_from_json_round_trips_to_kwargs():
    config = Sentinel1Config.from_json(S1_DATA)

    assert config.to_kwargs() == S1_DATA


def test_sentinel2_config_from_json_round_trips_to_kwargs():
    config = Sentinel2Config.from_json(S2_DATA)

    assert config.to_kwargs() == S2_DATA


def test_from_json_raises_on_missing_field():
    incomplete = {k: v for k, v in S1_DATA.items() if k != "orbit_direction"}

    with pytest.raises(ValueError, match="missing required field"):
        Sentinel1Config.from_json(incomplete)


def test_from_json_raises_on_unknown_field():
    # Guards against stale config keys, e.g. the pre-SQLite `relative_orbits_path`.
    extra = {**S2_DATA, "relative_orbits_path": "data/s2_relative_orbits.json"}

    with pytest.raises(ValueError, match="unrecognized field"):
        Sentinel2Config.from_json(extra)
