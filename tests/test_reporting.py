from pathlib import Path

from downloader.models import (
    DownloadStatus,
    FileDownloadResult,
    RunSummary,
    Sentinel2DownloadStatus,
    TileDownloadSummary,
)
from downloader.reporting import format_run_report, format_tile_report


def make_tile_summary():
    ok_product = Sentinel2DownloadStatus(
        product_id="a",
        product_name="A.SAFE",
        product_level="L2A",
        band_selection=["B02_10m"],
        files=[FileDownloadResult(Path("A.SAFE/B02_10m.jp2"), DownloadStatus.SUCCESS)],
    )
    failed_product = Sentinel2DownloadStatus(
        product_id="b",
        product_name="B.SAFE",
        product_level="L2A",
        band_selection=["B02_10m"],
        files=[
            FileDownloadResult(
                Path("B.SAFE/B02_10m.jp2"),
                DownloadStatus.FAILED,
                attempts=3,
                error="HTTP 500",
            ),
        ],
    )
    return TileDownloadSummary(tile_id="T19HCC", products=[ok_product, failed_product])


def test_format_tile_report_includes_counts_and_failure_reason():
    report = format_tile_report(make_tile_summary())

    assert "Tile T19HCC" in report
    assert "1 succeeded, 1 failed, 0 skipped" in report
    assert "A.SAFE [SUCCESS]" in report
    assert "B.SAFE [FAILED]" in report
    assert "FAILED: B.SAFE/B02_10m.jp2 - HTTP 500" in report


def test_format_tile_report_omits_successful_files_from_the_failure_list():
    report = format_tile_report(make_tile_summary())

    assert "FAILED: A.SAFE" not in report


def test_format_run_report_aggregates_across_tiles():
    run = RunSummary(tiles=[make_tile_summary(), make_tile_summary()])

    report = format_run_report(run)

    assert "Tiles: 2" in report
    assert "Succeeded: 2  Failed: 2  Skipped: 0" in report
    assert report.count("Tile T19HCC") == 2
