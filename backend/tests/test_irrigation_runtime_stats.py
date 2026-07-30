import json
from pathlib import Path

import pytest

from backend import irrigation_runtime_stats


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.fixture
def runtime_root(tmp_path):
    root = tmp_path / "irrigation_runtime"
    write_json(
        root / "manifest.json",
        {
            "schemaVersion": 1,
            "unit": "万m³",
            "artifacts": [
                "averages/county.json",
                "averages/township_by_county/130502.json",
                "series/county.json",
                "series/township_index.json",
                "series/township_by_source_code/130521.json",
            ],
        },
    )
    write_json(
        root / "averages/county.json",
        {
            "level": "county",
            "unit": "万m³",
            "averages": [
                {"regionId": "130502", "name": "桥东区", "average": 10}
            ],
            "legend": [],
        },
    )
    write_json(
        root / "averages/township_by_county/130502.json",
        {
            "level": "township",
            "unit": "万m³",
            "averages": [
                {
                    "regionId": "130521001000",
                    "name": "旧编码街道",
                    "average": 4,
                }
            ],
            "legend": [],
        },
    )
    write_json(
        root / "series/county.json",
        {
            "unit": "万m³",
            "regions": {
                "130502": {
                    "name": "桥东区",
                    "annual": [{"time": "2024", "value": 10}],
                    "monthly": [],
                }
            },
        },
    )
    write_json(
        root / "series/township_index.json",
        {"130521001000": "130521"},
    )
    write_json(
        root / "series/township_by_source_code/130521.json",
        {
            "130521001000": {
                "name": "旧编码街道",
                "annual": [{"time": "2024", "value": 4}],
                "monthly": [],
            }
        },
    )
    return root


@pytest.fixture(autouse=True)
def install_runtime_root(runtime_root, monkeypatch):
    monkeypatch.setattr(
        irrigation_runtime_stats,
        "IRRIGATION_RUNTIME_STATS_ROOT",
        runtime_root,
    )
    irrigation_runtime_stats.clear_runtime_stats_caches()
    yield
    irrigation_runtime_stats.clear_runtime_stats_caches()


def test_county_averages_load_from_core_file():
    payload = irrigation_runtime_stats.load_region_averages("county")

    assert payload["level"] == "county"
    assert payload["averages"][0]["regionId"] == "130502"


def test_township_averages_accept_prefixed_county_id():
    payload = irrigation_runtime_stats.load_region_averages(
        "township",
        "156130502",
    )

    assert payload["averages"][0]["regionId"] == "130521001000"


def test_township_series_uses_index_and_returns_defensive_copy():
    first = irrigation_runtime_stats.load_region_series_entry(
        "township",
        "130521001000",
    )
    assert first is not None
    unit, entry = first
    assert unit == "万m³"
    entry["annual"][0]["value"] = -1

    second = irrigation_runtime_stats.load_region_series_entry(
        "township",
        "130521001000",
    )
    assert second is not None
    assert second[1]["annual"][0]["value"] == 4


def test_county_series_lookup_and_unknown_region():
    result = irrigation_runtime_stats.load_region_series_entry(
        "county",
        "130502",
    )

    assert result is not None
    assert result[0] == "万m³"
    assert result[1]["name"] == "桥东区"
    assert (
        irrigation_runtime_stats.load_region_series_entry(
            "county",
            "missing",
        )
        is None
    )


def test_changed_shard_version_returns_fresh_content(runtime_root):
    first = irrigation_runtime_stats.load_region_series_entry(
        "township",
        "130521001000",
    )
    assert first is not None
    shard = (
        runtime_root
        / "series"
        / "township_by_source_code"
        / "130521.json"
    )
    write_json(
        shard,
        {
            "130521001000": {
                "name": "旧编码街道",
                "annual": [{"time": "2024", "value": 400}],
                "monthly": [{"time": "2024-01", "value": 1}],
            }
        },
    )

    second = irrigation_runtime_stats.load_region_series_entry(
        "township",
        "130521001000",
    )

    assert second is not None
    assert second[1]["annual"][0]["value"] == 400


def test_missing_or_malformed_artifact_raises_runtime_data_error(runtime_root):
    (runtime_root / "manifest.json").write_text("{", encoding="utf-8")

    with pytest.raises(
        irrigation_runtime_stats.IrrigationRuntimeDataError,
        match="manifest.json",
    ):
        irrigation_runtime_stats.load_region_series_entry(
            "township",
            "130521001000",
        )


def test_all_loaders_reject_unsupported_manifest_schema(runtime_root):
    write_json(
        runtime_root / "manifest.json",
        {"schemaVersion": 2, "unit": "万m³"},
    )

    with pytest.raises(
        irrigation_runtime_stats.IrrigationRuntimeDataError,
        match="schema",
    ):
        irrigation_runtime_stats.load_region_averages("county")


def test_series_shard_cache_is_bounded_to_64(runtime_root):
    index = {}
    for number in range(65):
        region_id = f"custom-{number}"
        shard_name = f"shard-{number}"
        index[region_id] = shard_name
        write_json(
            runtime_root
            / "series"
            / "township_by_source_code"
            / f"{shard_name}.json",
            {
                region_id: {
                    "name": region_id,
                    "annual": [],
                    "monthly": [],
                }
            },
        )
    write_json(runtime_root / "series/township_index.json", index)
    irrigation_runtime_stats.clear_runtime_stats_caches()

    for region_id in index:
        assert (
            irrigation_runtime_stats.load_region_series_entry(
                "township",
                region_id,
            )
            is not None
        )

    assert irrigation_runtime_stats._load_series_shard.cache_info().currsize == 64
