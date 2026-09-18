import sqlite3
from pathlib import Path

from downloader.config.path import PROJECT_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS s1_footprints (
    tile_id TEXT PRIMARY KEY,
    footprint TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS s2_orbits (
    tile_id TEXT PRIMARY KEY,
    relative_orbit TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS s2_tile_footprints (
    tile_id TEXT PRIMARY KEY,
    footprint TEXT NOT NULL
);
"""


def resolve_db_path(db_path: str | Path) -> Path:
    """Resolves a (possibly relative) db path against the project root."""
    path = Path(db_path)
    return path if path.is_absolute() else PROJECT_DIR / path


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """
    Opens a SQLite connection to `db_path`, creating the parent directory
    and the reference-data schema if they don't already exist.
    """
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection
