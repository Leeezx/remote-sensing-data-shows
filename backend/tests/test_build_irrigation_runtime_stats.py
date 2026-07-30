import math
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_irrigation_runtime_stats import (
    build_runtime_payloads,
    build_runtime_stats,
    main,
)


BASE_LEGEND = [
    {"value": index, "color": f"#{index}{index}{index}", "label": str(index)}
    for index in range(6)
]


def entry(name: str, *values: float) -> dict:
    return {
        "name": name,
        "annual": [
            {"time": str(2020 + index), "value": value}
            for index, value in enumerate(values)
        ],
        "monthly": [],
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def install_build_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "irrigation_region_series.json"
    regions = tmp_path / "irrigation_regions.json"
    layer = tmp_path / "irrigation_layer.json"
    chunks = tmp_path / "township_by_county"
    write_json(
        source,
        {
            "unit": "万m³",
            "county": {"130502": entry("桥东区", 10)},
            "township": {"130521001000": entry("旧编码街道", 4)},
        },
    )
    write_json(
        regions,
        [
            {"id": "130502", "name": "桥东区", "level": "county"},
            {
                "id": "130521001000",
                "name": "旧编码街道",
                "level": "township",
            },
        ],
    )
    write_json(layer, {"legend": BASE_LEGEND})
    write_json(
        chunks / "manifest.json",
        {
            "chunkCount": 1,
            "chunks": {
                "130502": {
                    "countyId": "156130502",
                    "featureCount": 1,
                    "bytes": 1,
                    "tolerance": 0.0005,
                }
            },
        },
    )
    write_json(
        chunks / "130502.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "id": "130521001000",
                        "parentId": "156130502",
                    },
                }
            ],
        },
    )
    return source, regions, layer, chunks


def test_runtime_payloads_follow_current_vector_ownership():
    series = {
        "unit": "万m³",
        "county": {"130502": entry("桥东区", 10, 20)},
        "township": {
            "130521001000": entry("旧编码街道", 3, 5),
            "custom-history-id": entry("历史区域", 7),
        },
    }
    regions = [
        {"id": "130502", "name": "桥东区", "level": "county"},
        {
            "id": "130521001000",
            "name": "旧编码街道",
            "level": "township",
        },
        {
            "id": "custom-history-id",
            "name": "历史区域",
            "level": "township",
        },
    ]

    result = build_runtime_payloads(
        series,
        regions,
        BASE_LEGEND,
        {
            "130502": {"130521001000"},
            "130503": {"130521001000"},
        },
        "source-digest",
    )

    assert result["averages/county.json"]["averages"] == [
        {"regionId": "130502", "name": "桥东区", "average": 15.0}
    ]
    assert result["averages/township_by_county/130502.json"]["averages"] == [
        {"regionId": "130521001000", "name": "旧编码街道", "average": 4.0}
    ]
    assert result["averages/township_by_county/130503.json"]["averages"] == [
        {"regionId": "130521001000", "name": "旧编码街道", "average": 4.0}
    ]
    assert result["series/township_index.json"] == {
        "130521001000": "130521",
        "custom-history-id": "misc",
    }
    assert set(result["series/township_by_source_code/130521.json"]) == {
        "130521001000"
    }
    assert set(result["series/township_by_source_code/misc.json"]) == {
        "custom-history-id"
    }
    manifest = result["manifest.json"]
    assert manifest["mappedTownshipPairCount"] == 2
    assert manifest["crossCountyTownshipCount"] == 1
    assert manifest["unmappedTownshipCount"] == 1


def test_runtime_payloads_preserve_missing_annual_average():
    result = build_runtime_payloads(
        {
            "unit": "万m³",
            "county": {"130502": entry("桥东区")},
            "township": {},
        },
        [{"id": "130502", "name": "桥东区", "level": "county"}],
        BASE_LEGEND,
        {},
        "digest",
    )

    assert result["averages/county.json"]["averages"][0]["average"] is None


def test_runtime_payloads_reject_unknown_vector_id():
    with pytest.raises(ValueError, match="missing from township series"):
        build_runtime_payloads(
            {"unit": "万m³", "county": {}, "township": {}},
            [],
            BASE_LEGEND,
            {"130502": {"130502001000"}},
            "digest",
        )


def test_runtime_payloads_reject_series_id_missing_from_catalog():
    with pytest.raises(ValueError, match="missing from region catalog"):
        build_runtime_payloads(
            {
                "unit": "万m³",
                "county": {"130502": entry("桥东区", 1)},
                "township": {},
            },
            [],
            BASE_LEGEND,
            {},
            "digest",
        )


def test_runtime_payloads_reject_non_finite_value():
    with pytest.raises(ValueError, match="finite"):
        build_runtime_payloads(
            {
                "unit": "万m³",
                "county": {"130502": entry("桥东区", math.inf)},
                "township": {},
            },
            [{"id": "130502", "name": "桥东区", "level": "county"}],
            BASE_LEGEND,
            {},
            "digest",
        )


def test_build_runtime_stats_publishes_valid_tree(tmp_path):
    source, regions, layer, chunks = install_build_inputs(tmp_path)
    output = tmp_path / "runtime"

    manifest = build_runtime_stats(
        source,
        regions,
        layer,
        chunks,
        output,
    )

    assert manifest["sourceTownshipCount"] == 1
    assert (output / "manifest.json").is_file()
    township_averages = json.loads(
        (
            output / "averages/township_by_county/130502.json"
        ).read_text(encoding="utf-8")
    )
    assert township_averages["averages"][0]["regionId"] == "130521001000"


def test_build_runtime_stats_keeps_previous_tree_when_validation_fails(tmp_path):
    source, regions, layer, chunks = install_build_inputs(tmp_path)
    output = tmp_path / "runtime"
    build_runtime_stats(source, regions, layer, chunks, output)
    before = {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    chunk = json.loads(
        (chunks / "130502.geojson").read_text(encoding="utf-8")
    )
    chunk["features"][0]["properties"]["id"] = "130502001000"
    write_json(chunks / "130502.geojson", chunk)

    with pytest.raises(ValueError, match="missing from township series"):
        build_runtime_stats(source, regions, layer, chunks, output)

    after = {
        path.relative_to(output).as_posix(): path.read_bytes()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_build_runtime_stats_rejects_parent_id_mismatch(tmp_path):
    source, regions, layer, chunks = install_build_inputs(tmp_path)
    output = tmp_path / "runtime"
    chunk = json.loads(
        (chunks / "130502.geojson").read_text(encoding="utf-8")
    )
    chunk["features"][0]["properties"]["parentId"] = "156130503"
    write_json(chunks / "130502.geojson", chunk)

    with pytest.raises(ValueError, match="parentId"):
        build_runtime_stats(source, regions, layer, chunks, output)


def test_check_mode_detects_artifact_drift(tmp_path):
    source, regions, layer, chunks = install_build_inputs(tmp_path)
    output = tmp_path / "runtime"
    build_runtime_stats(source, regions, layer, chunks, output)
    common_args = [
        "--source",
        str(source),
        "--regions",
        str(regions),
        "--layer",
        str(layer),
        "--township-root",
        str(chunks),
        "--output",
        str(output),
        "--check",
    ]

    assert main(common_args) == 0

    county_path = output / "averages/county.json"
    county_path.write_text('{"drift": true}', encoding="utf-8")

    assert main(common_args) == 1


def test_builder_cli_can_run_directly_from_project_root():
    project_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_irrigation_runtime_stats.py",
            "--help",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--township-root" in result.stdout
