import json
import sqlite3
from pathlib import Path

from downloader.storage.database import get_connection


class FootprintRepository:
    """Lookup of Sentinel-1 AOI footprints (tile_id -> polygon coordinates)."""

    def __init__(self, db_path: str | Path):
        self._connection: sqlite3.Connection = get_connection(db_path)

    def get(self, tile_id: str) -> list[str] | None:
        row = self._connection.execute(
            "SELECT footprint FROM s1_footprints WHERE tile_id = ?",
            (tile_id,),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def all(self) -> dict[str, list[str]]:
        rows = self._connection.execute(
            "SELECT tile_id, footprint FROM s1_footprints",
        ).fetchall()
        return {tile_id: json.loads(footprint) for tile_id, footprint in rows}

    def upsert(self, tile_id: str, footprint: list[str]) -> None:
        self._connection.execute(
            "INSERT INTO s1_footprints (tile_id, footprint) VALUES (?, ?) "
            "ON CONFLICT(tile_id) DO UPDATE "
            "SET footprint = excluded.footprint",
            (tile_id, json.dumps(footprint)),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()


class OrbitRepository:
    """Lookup of Sentinel-2 relative orbits (tile_id -> orbit number)."""

    def __init__(self, db_path: str | Path):
        self._connection: sqlite3.Connection = get_connection(db_path)

    def get(self, tile_id: str) -> str | None:
        row = self._connection.execute(
            "SELECT relative_orbit FROM s2_orbits WHERE tile_id = ?",
            (tile_id,),
        ).fetchone()
        return row[0] if row else None

    def all(self) -> dict[str, str]:
        rows = self._connection.execute(
            "SELECT tile_id, relative_orbit FROM s2_orbits",
        ).fetchall()
        return dict(rows)

    def upsert(self, tile_id: str, relative_orbit: str) -> None:
        self._connection.execute(
            "INSERT INTO s2_orbits (tile_id, relative_orbit) VALUES (?, ?) "
            "ON CONFLICT(tile_id) DO UPDATE "
            "SET relative_orbit = excluded.relative_orbit",
            (tile_id, relative_orbit),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
