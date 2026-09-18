import time
from unittest.mock import MagicMock

import requests

from downloader.downloaders.s2_downloader import Sentinel2
from downloader.models import DownloadStatus, TileDownloadSummary


def make_sentinel2(tmp_path, max_retries=3):
    downloader = Sentinel2(
        username="user",
        password="pass",
        tile_ids=["T19HCC"],
        product_level="L2A",
        db_path="data/sentinel.db",
        initial_date="2023-01-01",
        last_date="2023-01-31",
        band_selection=["B02_10m"],
        output_dir=str(tmp_path),
        max_retries=max_retries,
    )
    # Bypass the real Keycloak login: install a fake, unexpired session directly.
    downloader._session = MagicMock(spec=requests.Session)
    downloader._token_created_at = time.time()
    return downloader


def fake_response(status_code, content=b"file-bytes"):
    response = MagicMock()
    response.status_code = status_code
    response.iter_content.return_value = [content]
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(f"HTTP {status_code}")
    else:
        response.raise_for_status.return_value = None
    return response


def test_download_with_retries_succeeds_on_first_attempt(tmp_path):
    downloader = make_sentinel2(tmp_path)
    downloader.session.get.return_value = fake_response(200)
    file_path = tmp_path / "manifest.safe"

    result = downloader._download_with_retries("http://example.test/file", file_path)

    assert result.status == DownloadStatus.SUCCESS
    assert result.attempts == 1
    assert file_path.read_bytes() == b"file-bytes"


def test_download_with_retries_never_writes_a_failed_http_response(tmp_path):
    downloader = make_sentinel2(tmp_path)
    downloader.session.get.return_value = fake_response(404, content=b"<html>not found</html>")
    file_path = tmp_path / "manifest.safe"

    result = downloader._download_with_retries("http://example.test/file", file_path)

    assert result.status == DownloadStatus.FAILED
    assert result.attempts == downloader.max_retries
    assert "404" in result.error
    assert not file_path.exists()


def test_download_with_retries_succeeds_after_transient_failure(tmp_path):
    downloader = make_sentinel2(tmp_path, max_retries=3)
    downloader.session.get.side_effect = [fake_response(500), fake_response(200)]
    file_path = tmp_path / "manifest.safe"

    result = downloader._download_with_retries("http://example.test/file", file_path)

    assert result.status == DownloadStatus.SUCCESS
    assert result.attempts == 2
    assert file_path.read_bytes() == b"file-bytes"


def test_download_aggregates_download_tile_results_into_a_run_summary(tmp_path):
    downloader = make_sentinel2(tmp_path)
    downloader.tile_ids = ["T19HCC", "T19HCD"]
    tile_summaries = {
        "T19HCC": TileDownloadSummary(tile_id="T19HCC"),
        "T19HCD": TileDownloadSummary(tile_id="T19HCD"),
    }
    downloader.download_tile = lambda tile_id: tile_summaries[tile_id]

    run_summary = downloader.download()

    assert run_summary.tiles == [tile_summaries["T19HCC"], tile_summaries["T19HCD"]]
