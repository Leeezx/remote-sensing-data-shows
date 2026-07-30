import math

import pytest

from scripts.build_irrigation_runtime_stats import build_runtime_payloads


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
