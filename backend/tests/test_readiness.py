import json

from backend import readiness


def install_complete_runtime(monkeypatch, tmp_path):
    series = tmp_path / "stats" / "irrigation_region_series.json"
    series.parent.mkdir()
    series.write_text('{"county": {}}', encoding="utf-8")
    county = tmp_path / "vectors" / "county" / "china_county.shp"
    county.parent.mkdir(parents=True)
    for suffix in (".shp", ".shx", ".dbf"):
        county.with_suffix(suffix).write_bytes(b"x")
    township = tmp_path / "vectors" / "township_by_county"
    township.mkdir()
    (township / "manifest.json").write_text("{}", encoding="utf-8")
    raster_roots = []
    for name in (
        "ssm",
        "et",
        "sm_10cm",
        "sm_30cm",
        "sm_60cm",
        "sm_100cm",
        "irrigation_annual",
        "irrigation_8day",
    ):
        root = tmp_path / "rasters" / name
        root.mkdir(parents=True)
        (root / "sample.tif").write_bytes(b"x")
        raster_roots.append((name, root))
    monkeypatch.setattr(readiness, "IRRIGATION_REGION_SERIES_PATH", series)
    monkeypatch.setattr(readiness, "COUNTY_VECTOR_PATH", county)
    monkeypatch.setattr(readiness, "TOWNSHIP_CHUNK_ROOT", township)
    monkeypatch.setattr(readiness, "required_raster_roots", lambda: raster_roots)


def test_complete_runtime_is_ready(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    assert readiness.collect_readiness_failures() == []


def test_readiness_uses_identifiers_not_host_paths(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    readiness.IRRIGATION_REGION_SERIES_PATH.unlink()
    failures = readiness.collect_readiness_failures()
    assert failures == ["irrigation_region_series"]
    assert str(tmp_path) not in json.dumps(failures)
