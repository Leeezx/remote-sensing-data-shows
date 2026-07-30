import json

import pytest

from backend import readiness


def install_complete_runtime(monkeypatch, tmp_path):
    runtime = tmp_path / "stats" / "irrigation_runtime"
    runtime.mkdir(parents=True)
    for relative_path in (
        "manifest.json",
        "averages/county.json",
        "series/county.json",
        "series/township_index.json",
    ):
        target = runtime / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
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
    monkeypatch.setattr(readiness, "IRRIGATION_RUNTIME_STATS_ROOT", runtime)
    monkeypatch.setattr(readiness, "COUNTY_VECTOR_PATH", county)
    monkeypatch.setattr(readiness, "TOWNSHIP_CHUNK_ROOT", township)
    monkeypatch.setattr(readiness, "required_raster_roots", lambda: raster_roots)


def test_complete_runtime_is_ready(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    assert readiness.collect_readiness_failures() == []


def test_readiness_uses_identifiers_not_host_paths(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    (readiness.IRRIGATION_RUNTIME_STATS_ROOT / "manifest.json").unlink()
    failures = readiness.collect_readiness_failures()
    assert failures == ["irrigation_runtime_stats"]
    assert str(tmp_path) not in json.dumps(failures)


def test_malformed_runtime_manifest_is_not_ready(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    (
        readiness.IRRIGATION_RUNTIME_STATS_ROOT / "manifest.json"
    ).write_text("{", encoding="utf-8")

    assert readiness.collect_readiness_failures() == [
        "irrigation_runtime_stats"
    ]


@pytest.mark.parametrize(
    "relative_path",
    (
        "averages/county.json",
        "series/county.json",
        "series/township_index.json",
    ),
)
def test_missing_runtime_core_artifact_is_not_ready(
    monkeypatch,
    tmp_path,
    relative_path,
):
    install_complete_runtime(monkeypatch, tmp_path)
    (readiness.IRRIGATION_RUNTIME_STATS_ROOT / relative_path).unlink()

    assert readiness.collect_readiness_failures() == [
        "irrigation_runtime_stats"
    ]


@pytest.mark.parametrize(
    ("dependency", "remove_dependency"),
    [
        ("county_vector", lambda: readiness.COUNTY_VECTOR_PATH.unlink()),
        (
            "township_chunks",
            lambda: (readiness.TOWNSHIP_CHUNK_ROOT / "manifest.json").unlink(),
        ),
    ],
)
def test_missing_vector_dependency_is_reported(
    monkeypatch, tmp_path, dependency, remove_dependency
):
    install_complete_runtime(monkeypatch, tmp_path)
    remove_dependency()

    assert readiness.collect_readiness_failures() == [dependency]


def test_missing_raster_root_is_reported(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    raster_roots = readiness.required_raster_roots()
    missing_identifier, missing_root = raster_roots[0]
    (missing_root / "sample.tif").unlink()

    assert readiness.collect_readiness_failures() == [missing_identifier]
