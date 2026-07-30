import json
import sys

from backend import precompute_irrigation
from backend.precompute_irrigation import build_region_catalog


def test_build_region_catalog_preserves_both_levels_and_parent_ids():
    series_data = {
        "unit": "万m³",
        "county": {
            "county_b": {"name": "乙县", "annual": [], "monthly": []},
            "county_a": {"name": "甲县", "annual": [], "monthly": []},
        },
        "township": {
            "township_a2": {"name": "乙镇", "annual": [], "monthly": []},
            "township_a1": {"name": "甲镇", "annual": [], "monthly": []},
        },
    }
    previous = [
        {
            "id": "township_a1",
            "name": "旧名称",
            "level": "township",
            "parentId": "county_a",
        }
    ]

    assert build_region_catalog(series_data, previous) == [
        {"id": "county_a", "name": "甲县", "level": "county", "parentId": None},
        {"id": "county_b", "name": "乙县", "level": "county", "parentId": None},
        {
            "id": "township_a1",
            "name": "甲镇",
            "level": "township",
            "parentId": "county_a",
        },
        {
            "id": "township_a2",
            "name": "乙镇",
            "level": "township",
            "parentId": None,
        },
    ]


def test_build_region_catalog_ignores_unknown_sections_and_invalid_entries():
    series_data = {
        "unit": "万m³",
        "county": {"county_a": {"name": "甲县"}, "broken": "not-an-object"},
        "township": {},
        "province": {"province_a": {"name": "甲省"}},
    }

    assert build_region_catalog(series_data) == [
        {"id": "county_a", "name": "甲县", "level": "county", "parentId": None}
    ]


def install_complete_precompute_run(monkeypatch, tmp_path):
    output = tmp_path / "irrigation_region_series.json"
    regions = tmp_path / "irrigation_regions.json"
    shapefile = tmp_path / "county.shp"
    shapefile.write_bytes(b"x")
    output.write_text(
        json.dumps(
            {
                "unit": "万m³",
                "county": {
                    "130502": {
                        "name": "桥东区",
                        "annual": [{"time": "2024", "value": 1}],
                        "monthly": [{"time": "2024-01", "value": 1}],
                    }
                },
                "township": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(precompute_irrigation, "OUTPUT_PATH", output)
    monkeypatch.setattr(precompute_irrigation, "REGIONS_PATH", regions)
    monkeypatch.setattr(
        precompute_irrigation,
        "_LEVEL_SHAPEFILES",
        {"county": shapefile},
    )
    monkeypatch.setattr(
        precompute_irrigation,
        "read_shapefile_geojson",
        lambda path: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"id": "130502", "name": "桥东区"},
                    "geometry": {"type": "Polygon", "coordinates": []},
                }
            ],
        },
    )


def test_complete_precompute_run_publishes_runtime_stats(monkeypatch, tmp_path):
    install_complete_precompute_run(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        precompute_irrigation,
        "publish_runtime_stats",
        lambda: calls.append("published")
        or {
            "countyCount": 1,
            "mappedTownshipCount": 0,
            "crossCountyTownshipCount": 0,
            "unmappedTownshipCount": 0,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["precompute_irrigation.py", "--level", "county"],
    )

    precompute_irrigation.main()

    assert calls == ["published"]


def test_limited_precompute_run_does_not_publish_runtime_stats(
    monkeypatch,
    tmp_path,
):
    install_complete_precompute_run(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(
        precompute_irrigation,
        "publish_runtime_stats",
        lambda: calls.append("published"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "precompute_irrigation.py",
            "--level",
            "county",
            "--limit",
            "1",
        ],
    )

    precompute_irrigation.main()

    assert calls == []


def test_precompute_run_with_errors_does_not_publish_runtime_stats(
    monkeypatch,
    tmp_path,
):
    install_complete_precompute_run(monkeypatch, tmp_path)
    output = precompute_irrigation.OUTPUT_PATH
    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["county"]["130502"]["annual"] = None
    output.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(
        precompute_irrigation,
        "_annual_series",
        lambda geometry: (_ for _ in ()).throw(RuntimeError("broken")),
    )
    monkeypatch.setattr(
        precompute_irrigation,
        "publish_runtime_stats",
        lambda: calls.append("published"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["precompute_irrigation.py", "--level", "county"],
    )

    precompute_irrigation.main()

    assert calls == []
