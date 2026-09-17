from downloader.storage.repositories import FootprintRepository, OrbitRepository


def test_footprint_repository_round_trips_a_footprint(tmp_path):
    repo = FootprintRepository(tmp_path / "sentinel.db")
    footprint = ["-71.15 -33.42", "-71.17 -34.40", "-69.98 -34.42"]

    repo.upsert("T19HCC", footprint)

    assert repo.get("T19HCC") == footprint
    assert repo.all() == {"T19HCC": footprint}


def test_footprint_repository_returns_none_for_unknown_tile(tmp_path):
    repo = FootprintRepository(tmp_path / "sentinel.db")

    assert repo.get("UNKNOWN") is None
    assert repo.all() == {}


def test_footprint_repository_upsert_overwrites_existing_value(tmp_path):
    repo = FootprintRepository(tmp_path / "sentinel.db")
    repo.upsert("T19HCC", ["0 0"])

    repo.upsert("T19HCC", ["1 1", "2 2"])

    assert repo.get("T19HCC") == ["1 1", "2 2"]


def test_orbit_repository_round_trips_an_orbit(tmp_path):
    repo = OrbitRepository(tmp_path / "sentinel.db")

    repo.upsert("T19HCC", "R096")

    assert repo.get("T19HCC") == "R096"
    assert repo.all() == {"T19HCC": "R096"}


def test_orbit_repository_returns_none_for_unknown_tile(tmp_path):
    repo = OrbitRepository(tmp_path / "sentinel.db")

    assert repo.get("UNKNOWN") is None
    assert repo.all() == {}


def test_repositories_share_the_same_database_file(tmp_path):
    db_path = tmp_path / "sentinel.db"
    footprint_repo = FootprintRepository(db_path)
    orbit_repo = OrbitRepository(db_path)

    footprint_repo.upsert("T19HCC", ["0 0"])
    orbit_repo.upsert("T19HCC", "R096")

    assert footprint_repo.get("T19HCC") == ["0 0"]
    assert orbit_repo.get("T19HCC") == "R096"
