from dataclasses import replace

import pytest

from downloader.api import build_downloader, download_tile
from downloader.downloaders.s2_downloader import Sentinel2
from downloader.models import Sentinel2Config, TileDownloadSummary

BASE_S2_CONFIG = Sentinel2Config(
    initial_date="2018-01-01",
    last_date="2018-01-11",
    output_dir="Sentinel-2",
    max_retries=3,
    tile_ids=["T19HCC"],
    product_level="L2A",
    db_path="data/sentinel.db",
    band_selection=["B02_10m"],
)


def make_config(tmp_path, **overrides):
    return replace(BASE_S2_CONFIG, output_dir=str(tmp_path), **overrides)


def test_build_downloader_uses_explicit_credentials(tmp_path):
    config = make_config(tmp_path)

    downloader = build_downloader("s2", config, username="user", password="pass")

    assert isinstance(downloader, Sentinel2)
    assert downloader.username == "user"
    assert downloader.password == "pass"
    assert downloader.tile_ids == ["T19HCC"]


def test_build_downloader_accepts_a_plain_dict_config(tmp_path):
    config = make_config(tmp_path).to_kwargs()

    downloader = build_downloader("s2", config, username="user", password="pass")

    assert isinstance(downloader, Sentinel2)


def test_build_downloader_raises_without_credentials(tmp_path, monkeypatch):
    # Never let a real local .env leak real credentials into this test.
    monkeypatch.setattr("downloader.api.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("COPERNICUS_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUS_PASSWORD", raising=False)
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="credentials"):
        build_downloader("s2", config)


def test_download_tile_delegates_to_the_downloader_and_returns_its_summary(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    expected_summary = TileDownloadSummary(tile_id="T19KCP")
    monkeypatch.setattr(Sentinel2, "download_tile", lambda self, tile_id: expected_summary)

    summary = download_tile("s2", "T19KCP", username="user", password="pass", config=config)

    assert summary is expected_summary


def test_download_tile_fills_in_tile_ids_when_config_omits_them(tmp_path, monkeypatch):
    config = make_config(tmp_path, tile_ids=[])
    captured = {}

    def fake_download_tile(self, tile_id):
        captured["tile_ids"] = self.tile_ids
        return TileDownloadSummary(tile_id=tile_id)

    monkeypatch.setattr(Sentinel2, "download_tile", fake_download_tile)

    download_tile("s2", "T19KCP", username="user", password="pass", config=config)

    assert captured["tile_ids"] == ["T19KCP"]
