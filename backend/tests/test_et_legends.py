import importlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

BASE_LEGEND = [
    {"value": 0, "color": "#d53e4f", "label": "低"},
    {"value": 20, "color": "#fc8d59", "label": "较低"},
    {"value": 40, "color": "#fee08b", "label": "中等"},
    {"value": 60, "color": "#99d594", "label": "较高"},
    {"value": 80, "color": "#3288bd", "label": "高"},
    {"value": 100, "color": "#016c59", "label": "很高"},
]


def _et_legends():
    return importlib.import_module("backend.et_legends")


def test_build_et_legend_masks_invalid_raw_values_before_scaling():
    et_legends = _et_legends()
    values = np.array([0, 100, 200, 300, 400, 500, 600, -999, np.nan])
    source_mask = np.array([255, 255, 255, 255, 255, 255, 255, 255, 255])

    result = et_legends.build_et_legend(
        values,
        BASE_LEGEND,
        "mm/8天",
        source_mask=source_mask,
        nodata=-999,
        value_scale=0.1,
        nodata_values=(0,),
    )

    expected = np.percentile(
        np.array([10, 20, 30, 40, 50, 60], dtype=float),
        np.linspace(2, 98, 6),
    )
    np.testing.assert_allclose([item["value"] for item in result], expected)
    assert [item["color"] for item in result] == [
        item["color"] for item in BASE_LEGEND
    ]
    assert all(item["label"].endswith("mm/8天") for item in result)


def test_build_et_legend_falls_back_when_six_distinct_stops_are_impossible():
    et_legends = _et_legends()
    result = et_legends.build_et_legend(
        np.ones(100),
        BASE_LEGEND,
        "mm/8天",
    )

    assert result == BASE_LEGEND
    assert result is not BASE_LEGEND


def _document(value_offset: float = 0) -> dict:
    return {
        "version": 1,
        "legends": {
            "2010-01-01": [
                {
                    "value": value_offset + index + 1,
                    "color": item["color"],
                    "label": f"{value_offset + index + 1:.1f} mm/8天",
                }
                for index, item in enumerate(BASE_LEGEND)
            ]
        },
    }


def test_get_precomputed_et_legend_reuses_file_cache_and_returns_copies(
    monkeypatch, tmp_path
):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")
    reads = []
    original = Path.read_text

    def tracked_read(self, *args, **kwargs):
        reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read)

    first = et_legends.get_precomputed_et_legend("2010-01-01", path)
    first[0]["value"] = -1
    second = et_legends.get_precomputed_et_legend("2010-01-01", path)

    assert second[0]["value"] == 1
    assert reads == [path.resolve()]


def test_get_precomputed_et_legend_refreshes_after_atomic_replacement(tmp_path):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    replacement = tmp_path / "replacement.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")
    first = et_legends.get_precomputed_et_legend("2010-01-01", path)
    replacement.write_text(json.dumps(_document(10)), encoding="utf-8")
    os.replace(replacement, path)

    second = et_legends.get_precomputed_et_legend("2010-01-01", path)

    assert first[0]["value"] == 1
    assert second[0]["value"] == 11


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"version": 2, "legends": {}}, "Unsupported ET legend version"),
        ({"version": 1, "legends": []}, "legends must be an object"),
        (
            {"version": 1, "legends": {"2010-01-01": []}},
            "must contain exactly 6 items",
        ),
    ],
)
def test_invalid_et_legend_document_is_rejected(document, message, tmp_path):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(et_legends.ETLegendUnavailableError, match=message):
        et_legends.get_precomputed_et_legend("2010-01-01", path)


def test_missing_time_is_rejected_without_dynamic_fallback(tmp_path):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")

    with pytest.raises(
        et_legends.ETLegendUnavailableError,
        match="No precomputed ET legend for time '2010-01-09'",
    ):
        et_legends.get_precomputed_et_legend("2010-01-09", path)


def test_validate_et_legend_document_returns_normalized_immutable_entries():
    et_legends = _et_legends()

    result = et_legends.validate_et_legend_document(_document())

    assert result["2010-01-01"] == tuple(
        (float(index + 1), item["color"], f"{index + 1:.1f} mm/8天")
        for index, item in enumerate(BASE_LEGEND)
    )


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ([], "document must be an object"),
        (
            {"version": 1, "legends": {"2010-1-1": _document()["legends"]["2010-01-01"]}},
            "must be an ISO date",
        ),
        (
            {"version": 1, "legends": {"2010-01-01": "invalid"}},
            "must contain exactly 6 items",
        ),
        (
            {
                "version": 1,
                "legends": {
                    "2010-01-01": [
                        None,
                        *_document()["legends"]["2010-01-01"][1:],
                    ]
                },
            },
            "item 1 must be an object",
        ),
        (
            {
                "version": 1,
                "legends": {
                    "2010-01-01": [
                        {**_document()["legends"]["2010-01-01"][0], "value": True},
                        *_document()["legends"]["2010-01-01"][1:],
                    ]
                },
            },
            "item 1 value must be a finite number",
        ),
        (
            {
                "version": 1,
                "legends": {
                    "2010-01-01": [
                        {**_document()["legends"]["2010-01-01"][0], "value": np.inf},
                        *_document()["legends"]["2010-01-01"][1:],
                    ]
                },
            },
            "item 1 value must be a finite number",
        ),
        (
            {
                "version": 1,
                "legends": {
                    "2010-01-01": [
                        {**_document()["legends"]["2010-01-01"][0], "color": 123},
                        *_document()["legends"]["2010-01-01"][1:],
                    ]
                },
            },
            "item 1 color must be a string",
        ),
        (
            {
                "version": 1,
                "legends": {
                    "2010-01-01": [
                        {**_document()["legends"]["2010-01-01"][0], "label": None},
                        *_document()["legends"]["2010-01-01"][1:],
                    ]
                },
            },
            "item 1 label must be a string",
        ),
        (
            {
                "version": 1,
                "legends": {
                    "2010-01-01": [
                        *_document()["legends"]["2010-01-01"][:1],
                        {
                            **_document()["legends"]["2010-01-01"][1],
                            "value": 1,
                        },
                        *_document()["legends"]["2010-01-01"][2:],
                    ]
                },
            },
            "values must be strictly increasing",
        ),
    ],
)
def test_validate_et_legend_document_rejects_malformed_entries(document, message):
    et_legends = _et_legends()

    with pytest.raises(et_legends.ETLegendUnavailableError, match=message):
        et_legends.validate_et_legend_document(document)
