"""Tests for data-driven SSM legend thresholds."""

from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time

import numpy as np
import pytest

import backend.ssm_legend as ssm_legend
from backend.ssm_legend import build_dynamic_legend, get_dynamic_legend


BASE_LEGEND = [
    {"value": 0.09, "color": "#d53e4f", "label": "Dry"},
    {"value": 0.15, "color": "#fc8d59", "label": "Low"},
    {"value": 0.22, "color": "#fee08b", "label": "Moderate"},
    {"value": 0.28, "color": "#99d594", "label": "Moist"},
    {"value": 0.35, "color": "#3288bd", "label": "Wet"},
    {"value": 0.40, "color": "#016c59", "label": "Saturated"},
]


@pytest.fixture(autouse=True)
def clear_legend_cache():
    ssm_legend._cached_dynamic_legend.cache_clear()
    yield
    ssm_legend._cached_dynamic_legend.cache_clear()


def test_build_dynamic_legend_uses_p2_p98_and_six_even_stops():
    values = np.arange(100, dtype=float)

    result = build_dynamic_legend(values, BASE_LEGEND, "m3/m3")

    expected = np.linspace(1.98, 97.02, 6)
    np.testing.assert_allclose([item["value"] for item in result], expected)
    assert all(type(item["value"]) is float for item in result)


def test_build_dynamic_legend_preserves_colors_and_formats_labels():
    result = build_dynamic_legend(np.arange(100, dtype=float), BASE_LEGEND, "m3/m3")

    assert [item["color"] for item in result] == [item["color"] for item in BASE_LEGEND]
    assert [item["label"] for item in result] == [
        f"{item['value']:.3f} m3/m3" for item in result
    ]


def test_build_dynamic_legend_excludes_all_invalid_pixel_types():
    values = np.array([0.0, 50.0, 100.0, -999.0, -32768.0, np.nan, np.inf, -np.inf])
    source_mask = np.array([255, 0, 255, 255, 255, 255, 255, 255], dtype=np.uint8)

    result = build_dynamic_legend(
        values,
        BASE_LEGEND,
        "",
        source_mask=source_mask,
        nodata=-32768.0,
    )

    assert result[0]["value"] == pytest.approx(2.0)
    assert result[-1]["value"] == pytest.approx(98.0)
    assert result[0]["label"] == "2.000"


@pytest.mark.parametrize(
    "values",
    [
        np.array([np.nan, np.inf, -999.0]),
        np.array([4.2, 4.2, 4.2]),
    ],
)
def test_build_dynamic_legend_falls_back_for_no_valid_data_or_constant_data(values):
    result = build_dynamic_legend(values, BASE_LEGEND, "m3/m3")

    assert result == BASE_LEGEND
    assert result is not BASE_LEGEND
    assert all(actual is not original for actual, original in zip(result, BASE_LEGEND))


def test_build_dynamic_legend_falls_back_when_base_legend_is_not_six_stops():
    short_legend = BASE_LEGEND[:5]

    result = build_dynamic_legend(np.arange(100), short_legend, "m3/m3")

    assert result == short_legend
    assert result is not short_legend


def test_build_dynamic_legend_falls_back_when_percentiles_overflow():
    maximum = np.finfo(float).max

    with np.errstate(over="ignore", invalid="ignore"):
        result = build_dynamic_legend(
            np.array([-maximum] * 50 + [maximum] * 50),
            BASE_LEGEND,
            "m3/m3",
        )

    assert result == BASE_LEGEND
    assert result is not BASE_LEGEND
    assert all(actual is not original for actual, original in zip(result, BASE_LEGEND))


class _FakeDataset:
    nodata = -32768.0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, band):
        assert band == 1
        return np.arange(100, dtype=float).reshape(10, 10)

    def read_masks(self, band):
        assert band == 1
        return np.full((10, 10), 255, dtype=np.uint8)


def _install_fake_raster(monkeypatch):
    calls = []

    def fake_open(path):
        calls.append(path)
        return _FakeDataset()

    monkeypatch.setattr(ssm_legend.rasterio, "open", fake_open)
    return calls


def test_get_dynamic_legend_reuses_cache_and_returns_fresh_defensive_results(tmp_path, monkeypatch):
    path = tmp_path / "ssm.tif"
    path.write_bytes(b"fake")
    calls = _install_fake_raster(monkeypatch)

    first = get_dynamic_legend(path, BASE_LEGEND, "m3/m3")
    second = get_dynamic_legend(path, BASE_LEGEND, "m3/m3")

    assert len(calls) == 1
    assert first == second
    assert first is not second
    assert all(left is not right for left, right in zip(first, second))
    first[0]["value"] = -1
    assert second[0]["value"] == pytest.approx(1.98)


def test_get_dynamic_legend_coalesces_concurrent_cold_cache_misses(tmp_path, monkeypatch):
    path = tmp_path / "ssm.tif"
    path.write_bytes(b"fake")
    reader_started = threading.Event()
    release_reader = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def slow_reader(resolved_path):
        nonlocal calls
        assert resolved_path == str(path.resolve())
        with calls_lock:
            calls += 1
        reader_started.set()
        assert release_reader.wait(timeout=5)
        return (
            np.arange(100, dtype=float).reshape(10, 10),
            np.full((10, 10), 255, dtype=np.uint8),
            -32768.0,
        )

    monkeypatch.setattr(ssm_legend, "_read_dynamic_legend", slow_reader)
    with ThreadPoolExecutor(max_workers=4) as executor:
        first_future = executor.submit(get_dynamic_legend, path, BASE_LEGEND, "m3/m3")
        assert reader_started.wait(timeout=5)
        other_futures = [
            executor.submit(get_dynamic_legend, path, BASE_LEGEND, "m3/m3")
            for _ in range(3)
        ]
        deadline = time.monotonic() + 0.5
        while calls == 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        release_reader.set()
        results = [first_future.result(), *(future.result() for future in other_futures)]

    assert calls == 1
    assert all(result == results[0] for result in results)
    assert len({id(result) for result in results}) == len(results)
    assert all(
        len({id(result[index]) for result in results}) == len(results)
        for index in range(6)
    )


def test_get_dynamic_legend_invalidates_cache_when_mtime_changes(tmp_path, monkeypatch):
    path = tmp_path / "ssm.tif"
    path.write_bytes(b"fake")
    calls = _install_fake_raster(monkeypatch)

    get_dynamic_legend(path, BASE_LEGEND, "m3/m3")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    get_dynamic_legend(path, BASE_LEGEND, "m3/m3")

    assert len(calls) == 2


def test_get_dynamic_legend_invalidates_cache_when_palette_changes(tmp_path, monkeypatch):
    path = tmp_path / "ssm.tif"
    path.write_bytes(b"fake")
    calls = _install_fake_raster(monkeypatch)
    changed = [dict(item) for item in BASE_LEGEND]
    changed[0]["color"] = "#000000"

    first = get_dynamic_legend(path, BASE_LEGEND, "m3/m3")
    second = get_dynamic_legend(path, changed, "m3/m3")

    assert len(calls) == 2
    assert first[0]["color"] == "#d53e4f"
    assert second[0]["color"] == "#000000"
