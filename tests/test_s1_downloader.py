from downloader.downloaders.s1_downloader import Sentinel1


def make_sentinel1(tmp_path, polarization_mode):
    return Sentinel1(
        username="user",
        password="pass",
        db_path="data/sentinel.db",
        orbit_direction="DESCENDING",
        product_type="GRD",
        polarization_mode=polarization_mode,
        initial_date="2023-01-01",
        last_date="2023-01-31",
        output_dir=str(tmp_path),
        max_retries=1,
    )


FILES = [
    "measurement/s1a-iw-grd-vh-20230101.tiff",
    "measurement/s1a-iw-grd-vv-20230101.tiff",
    "annotation/s1a-iw-grd-vh-20230101.xml",
    "annotation/s1a-iw-grd-vv-20230101.xml",
    "annotation/calibration/calibration-s1a-iw-grd-vh-20230101.xml",
]


def test_filter_images_keeps_only_requested_polarizations(tmp_path):
    downloader = make_sentinel1(tmp_path, polarization_mode=["VV"])

    filtered = downloader.filter_images(FILES)

    assert filtered == [
        "measurement/s1a-iw-grd-vv-20230101.tiff",
        "annotation/s1a-iw-grd-vv-20230101.xml",
    ]


def test_filter_images_keeps_all_requested_polarizations(tmp_path):
    downloader = make_sentinel1(tmp_path, polarization_mode=["VV", "VH"])

    filtered = downloader.filter_images(FILES)

    assert filtered == FILES


def test_get_query_formats_without_error(tmp_path):
    downloader = make_sentinel1(tmp_path, polarization_mode=["VV"])

    query = downloader.get_query("T19HCC", "2023-01-01", "2023-01-31")

    assert "SENTINEL-1" in query
    assert "DESCENDING" in query
    assert "GRD" in query
    assert "{self." not in query
