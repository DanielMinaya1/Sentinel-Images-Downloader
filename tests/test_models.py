from pathlib import Path

from downloader.models import (
    DownloadStatus,
    FileDownloadResult,
    Sentinel1DownloadStatus,
    Sentinel1Response,
    Sentinel2DownloadStatus,
    Sentinel2Response,
    SentinelProduct,
    SentinelResponse,
    TileDownloadSummary,
)


ODATA_PAYLOAD = {
    "value": [
        {
            "Id": "abc-123",
            "Name": "S2A_MSIL2A_20230115.SAFE",
            "ContentDate": {"Start": "2023-01-15T00:00:00Z", "End": "2023-01-15T00:05:00Z"},
            "Online": True,
        },
        {
            "Id": "def-456",
            "Name": "S2A_MSIL2A_20230201.SAFE",
        },
    ]
}


class TestSentinelProduct:
    def test_from_json_parses_all_fields(self):
        product = SentinelProduct.from_json(ODATA_PAYLOAD["value"][0])

        assert product.id == "abc-123"
        assert product.name == "S2A_MSIL2A_20230115.SAFE"
        assert product.content_date_start == "2023-01-15T00:00:00Z"
        assert product.content_date_end == "2023-01-15T00:05:00Z"
        assert product.online is True

    def test_from_json_tolerates_missing_optional_fields(self):
        product = SentinelProduct.from_json(ODATA_PAYLOAD["value"][1])

        assert product.id == "def-456"
        assert product.content_date_start is None
        assert product.online is None


class TestSentinelResponse:
    def test_from_json_wraps_all_products(self):
        response = SentinelResponse.from_json(ODATA_PAYLOAD)

        assert len(response) == 2
        assert [p.id for p in response] == ["abc-123", "def-456"]

    def test_from_json_handles_empty_value(self):
        response = SentinelResponse.from_json({"value": []})

        assert len(response) == 0

    def test_satellite_subclasses_parse_the_same_payload(self):
        s1 = Sentinel1Response.from_json(ODATA_PAYLOAD)
        s2 = Sentinel2Response.from_json(ODATA_PAYLOAD)

        assert isinstance(s1, Sentinel1Response)
        assert isinstance(s2, Sentinel2Response)
        assert [p.id for p in s1] == [p.id for p in s2]


class TestSentinelDownloadStatus:
    def test_status_is_success_when_all_files_succeed(self):
        status = Sentinel2DownloadStatus(
            product_id="abc-123",
            product_name="S2A_MSIL2A_20230115.SAFE",
            product_level="L2A",
            band_selection=["B02_10m"],
            files=[
                FileDownloadResult(Path("manifest.safe"), DownloadStatus.SUCCESS, attempts=1),
                FileDownloadResult(Path("B02_10m.jp2"), DownloadStatus.SUCCESS, attempts=1),
            ],
        )

        assert status.status == DownloadStatus.SUCCESS
        assert status.succeeded == 2
        assert status.failed == 0

    def test_status_is_failed_when_any_file_fails(self):
        status = Sentinel1DownloadStatus(
            product_id="abc-123",
            product_name="S1A_IW_GRDH.SAFE",
            orbit_direction="DESCENDING",
            polarization_mode=["VV", "VH"],
            files=[
                FileDownloadResult(Path("manifest.safe"), DownloadStatus.SUCCESS, attempts=1),
                FileDownloadResult(
                    Path("measurement/vh.tiff"), DownloadStatus.FAILED, attempts=3, error="HTTP 500"
                ),
            ],
        )

        assert status.status == DownloadStatus.FAILED
        assert status.succeeded == 1
        assert status.failed == 1

    def test_status_is_skipped_when_no_files_were_needed(self):
        status = Sentinel2DownloadStatus(product_id="abc-123", product_name="S2.SAFE")

        assert status.status == DownloadStatus.SKIPPED

    def test_status_is_failed_when_manifest_download_itself_errors(self):
        status = Sentinel2DownloadStatus(
            product_id="abc-123", product_name="S2.SAFE", error="manifest download failed: HTTP 404"
        )

        assert status.status == DownloadStatus.FAILED


class TestTileDownloadSummary:
    def test_aggregates_counts_across_products(self):
        product_a = Sentinel2DownloadStatus(
            product_id="a",
            product_name="A.SAFE",
            files=[FileDownloadResult(Path("a.jp2"), DownloadStatus.SUCCESS)],
        )
        product_b = Sentinel2DownloadStatus(
            product_id="b",
            product_name="B.SAFE",
            files=[
                FileDownloadResult(Path("b1.jp2"), DownloadStatus.FAILED, error="boom"),
                FileDownloadResult(Path("b2.jp2"), DownloadStatus.SKIPPED),
            ],
        )
        summary = TileDownloadSummary(tile_id="T19HCC", products=[product_a, product_b])

        assert summary.succeeded == 1
        assert summary.failed == 1
        assert summary.skipped == 1
