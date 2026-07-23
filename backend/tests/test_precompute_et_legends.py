import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from backend.external_rasters import RasterSource


BASE_LEGEND = [
    {"value": 0, "color": "#d53e4f", "label": "低"},
    {"value": 20, "color": "#fc8d59", "label": "较低"},
    {"value": 40, "color": "#fee08b", "label": "中等"},
    {"value": 60, "color": "#99d594", "label": "较高"},
    {"value": 80, "color": "#3288bd", "label": "高"},
    {"value": 100, "color": "#016c59", "label": "很高"},
]


def _precomputer():
    return importlib.import_module("backend.precompute_et_legends")


def _write_period(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(100, 40, 0.01, 0.01),
        nodata=0,
        tiled=True,
        blockxsize=16,
        blockysize=16,
    ) as dataset:
        dataset.write(values.astype("uint16"), 1)


def test_build_document_is_sorted_complete_and_scaled(tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    values = np.arange(1, 257, dtype=np.uint16).reshape(16, 16)
    _write_period(root / "2010_8day_02_cog.tif", values + 10)
    _write_period(root / "2010_8day_01_cog.tif", values)

    document = precompute_et_legends.build_et_legend_document(
        root, BASE_LEGEND, "mm/8天"
    )

    assert document["version"] == 1
    assert len(document["legends"]) == 184
    assert list(document["legends"])[:2] == ["2010-01-01", "2010-01-09"]
    assert list(document["legends"])[-1] == "2013-12-27"
    assert len(document["legends"]["2010-01-01"]) == 6
    assert document["legends"]["2010-01-01"][0]["value"] < 10
    assert document["legends"]["2010-01-17"] == BASE_LEGEND


def test_duplicate_period_files_are_a_hard_failure(tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    values = np.arange(1, 257, dtype=np.uint16).reshape(16, 16)
    _write_period(root / "2010_01_cog.tif", values)
    _write_period(root / "2010_8day_01_cog.tif", values)

    with pytest.raises(ValueError, match="Duplicate raster files"):
        precompute_et_legends.build_et_legend_document(
            root, BASE_LEGEND, "mm/8天"
        )


def test_empty_root_is_a_hard_failure(tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "missing-et"

    with pytest.raises(ValueError) as exc_info:
        precompute_et_legends.build_et_legend_document(
            root, BASE_LEGEND, "mm/8天"
        )
    assert str(exc_info.value) == f"No ET period rasters found under '{root}'"


def test_period_outside_canonical_timeline_is_a_hard_failure(tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    _write_period(
        root / "2014_8day_01_cog.tif",
        np.arange(1, 257, dtype=np.uint16).reshape(16, 16),
    )

    with pytest.raises(ValueError, match="outside the 2010-2013 timeline"):
        precompute_et_legends.build_et_legend_document(
            root, BASE_LEGEND, "mm/8天"
        )


def test_constant_period_uses_base_legend_and_logs_warning(caplog, tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    _write_period(
        root / "2010_8day_01_cog.tif",
        np.ones((16, 16), dtype=np.uint16),
    )

    document = precompute_et_legends.build_et_legend_document(
        root, BASE_LEGEND, "mm/8天"
    )

    assert document["legends"]["2010-01-01"] == BASE_LEGEND
    assert "base legend" in caplog.text


def test_missing_period_uses_independent_base_copy_and_logs_warning(
    caplog, tmp_path
):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    _write_period(
        root / "2010_8day_01_cog.tif",
        np.arange(1, 257, dtype=np.uint16).reshape(16, 16),
    )

    document = precompute_et_legends.build_et_legend_document(
        root, BASE_LEGEND, "mm/8天"
    )

    missing = document["legends"]["2010-01-09"]
    another_missing = document["legends"]["2010-01-17"]
    assert missing == BASE_LEGEND
    assert missing is not BASE_LEGEND
    assert missing is not another_missing
    assert missing[0] is not another_missing[0]
    assert "Missing ET raster for 2010-01-09; using base legend" in caplog.text


def test_read_et_sample_limits_each_dimension_to_512(tmp_path):
    precompute_et_legends = _precomputer()
    path = tmp_path / "2010_8day_01_cog.tif"
    values = np.arange(700 * 900, dtype=np.uint32).reshape(700, 900) % 65535
    _write_period(path, values.astype(np.uint16))

    sampled_values, sampled_mask, nodata = precompute_et_legends.read_et_sample(
        RasterSource(path, 1)
    )

    assert sampled_values.shape == (512, 512)
    assert sampled_mask.shape == (512, 512)
    assert sampled_values.dtype == np.uint16
    assert nodata == 0


def test_read_et_sample_returns_raw_unscaled_values(tmp_path):
    precompute_et_legends = _precomputer()
    path = tmp_path / "2010_8day_01_cog.tif"
    values = np.arange(1, 257, dtype=np.uint16).reshape(16, 16)
    _write_period(path, values)

    sampled_values, sampled_mask, nodata = precompute_et_legends.read_et_sample(
        RasterSource(path, 1)
    )

    assert np.array_equal(sampled_values, values)
    assert np.all(sampled_mask == 255)
    assert nodata == 0


def test_atomic_write_preserves_previous_document_on_failure(
    monkeypatch, tmp_path
):
    precompute_et_legends = _precomputer()
    output = tmp_path / "stats" / "et_legends.json"
    output.parent.mkdir(parents=True)
    output.write_text('{"previous": true}', encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("injected replace failure")

    monkeypatch.setattr(precompute_et_legends.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        precompute_et_legends.write_et_legend_document(
            {"version": 1, "legends": {}}, output
        )

    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []


def test_atomic_write_fsyncs_before_replace(monkeypatch, tmp_path):
    precompute_et_legends = _precomputer()
    output = tmp_path / "stats" / "et_legends.json"
    events = []
    real_fsync = precompute_et_legends.os.fsync
    real_replace = precompute_et_legends.os.replace

    def record_fsync(file_descriptor):
        events.append("fsync")
        real_fsync(file_descriptor)

    def record_replace(source, destination):
        events.append("replace")
        assert Path(source).parent == output.parent
        assert Path(source).name.startswith(f".{output.name}.")
        real_replace(source, destination)

    monkeypatch.setattr(precompute_et_legends.os, "fsync", record_fsync)
    monkeypatch.setattr(precompute_et_legends.os, "replace", record_replace)

    precompute_et_legends.write_et_legend_document(
        {"version": 1, "legends": {}}, output
    )

    assert events == ["fsync", "replace"]
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "version": 1,
        "legends": {},
    }


def test_cli_writes_complete_document_and_reports_source_count(capsys, tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    output = tmp_path / "stats" / "et_legends.json"
    _write_period(
        root / "2010_8day_01_cog.tif",
        np.arange(1, 257, dtype=np.uint16).reshape(16, 16),
    )

    result = precompute_et_legends.main(
        ["--root", str(root), "--output", str(output)]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert "1 ET period raster" in captured.out
    assert str(output) in captured.out
    assert len(json.loads(output.read_text(encoding="utf-8"))["legends"]) == 184


def test_cli_returns_nonzero_when_et_metadata_is_missing(
    capsys, monkeypatch, tmp_path
):
    precompute_et_legends = _precomputer()
    monkeypatch.setattr(precompute_et_legends, "get_layer", lambda _layer_id: None)

    result = precompute_et_legends.main(
        [
            "--root",
            str(tmp_path / "et"),
            "--output",
            str(tmp_path / "et_legends.json"),
        ]
    )

    assert result != 0
    assert "ET layer metadata" in capsys.readouterr().err
