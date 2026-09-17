from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class SentinelConfig:
    """Fields shared by every satellite's download configuration."""

    initial_date: str
    last_date: str
    output_dir: str
    max_retries: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SentinelConfig":
        """
        Builds a config from a parsed JSON dict
        (e.g. examples/*_default_config.json), raising on missing
        or unrecognized fields instead of silently accepting a typo'd
        or stale config key.
        """
        field_names = {f.name for f in fields(cls)}
        missing = field_names - data.keys()
        unknown = data.keys() - field_names

        if missing:
            raise ValueError(f"{cls.__name__}: missing required field(s): {sorted(missing)}")
        if unknown:
            raise ValueError(f"{cls.__name__}: unrecognized field(s): {sorted(unknown)}")

        return cls(**{name: data[name] for name in field_names})

    def to_kwargs(self) -> dict[str, Any]:
        """Returns this config as keyword arguments for its downloader class."""
        return asdict(self)


@dataclass
class Sentinel1Config(SentinelConfig):
    db_path: str
    orbit_direction: str
    product_type: str
    polarization_mode: list[str]


@dataclass
class Sentinel2Config(SentinelConfig):
    tile_ids: list[str]
    product_level: str
    db_path: str
    band_selection: list[str]
