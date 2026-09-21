"""Tests for the water-demand artifact builder."""

import gzip
import json
from pathlib import Path

import numpy as np
from openpyxl import Workbook
import pytest

import scripts.build_water_demand_data as builder
from scripts.build_water_demand_data import (
    EXPECTED_COLUMNS,
    MAGIC,
    BuildError,
    binary_offsets,
    build_grid,
    decode_points,
    encode_points,
    quantize_values,
    read_workbook_points,
)


def write_workbook(path: Path, rows, header=None) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(list(EXPECTED_COLUMNS) if header is None else header)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path


def sample_rows(step: float = 0.01, size: int = 3):
    rows = []
    for i in range(size):
        for j in range(size):
            rows.append([
                100.0 + i * step,
                30.0 + j * step,
                1 + ((i + j) % 3),
                10.0 + i,
                20.0 + j,
                30.0 + i + j,
                40.0 + i,
                50.0 + j,
                60.0 + i + j,
            ])
    return rows


def square_geometry(min_x=99.0, min_y=29.0, max_x=104.0, max_y=34.0) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_x, min_y], [max_x, min_y], [max_x, max_y], [min_x, max_y], [min_x, min_y],
        ]],
    }


def test_read_workbook_points_requires_the_exact_header(tmp_path):
    path = write_workbook(tmp_path / "wrong.xlsx", sample_rows(), header=["a", "b", "c", "d", "e", "f", "g", "h", "i"])

    with pytest.raises(BuildError, match="header must be exactly"):
        read_workbook_points(path)


def test_read_workbook_points_rejects_duplicate_coordinates(tmp_path):
    rows = sample_rows()
    rows.append(list(rows[0]))
    path = write_workbook(tmp_path / "dupes.xlsx", rows)

    with pytest.raises(BuildError, match="duplicate coordinate"):
        read_workbook_points(path)


@pytest.mark.parametrize("column,value", [(0, 200.0), (1, 95.0)])
def test_read_workbook_points_rejects_out_of_range_coordinates(tmp_path, column, value):
    rows = sample_rows()
    rows[0][column] = value
    path = write_workbook(tmp_path / "range.xlsx", rows)

    with pytest.raises(BuildError, match="outside"):
        read_workbook_points(path)


def test_read_workbook_points_requires_known_class_values(tmp_path):
    rows = sample_rows()
    rows[0][2] = 7
    path = write_workbook(tmp_path / "cls.xlsx", rows)

    with pytest.raises(BuildError, match="Class must be one of"):
        read_workbook_points(path)


def test_read_workbook_points_returns_columns_in_source_order(tmp_path):
    path = write_workbook(tmp_path / "ok.xlsx", sample_rows())

    points = read_workbook_points(path)

    assert points["longitude"].shape == (9,)
    assert points["class"].dtype == np.uint8
    assert points["values"].shape == (6, 9)
    assert points["values"][0, 0] == pytest.approx(10.0)


def test_build_grid_resolves_axes_and_sorts_row_major():
    longitude = np.array([100.0, 100.01, 100.0, 100.01])
    latitude = np.array([30.0, 30.0, 30.01, 30.01])

    grid = build_grid(longitude, latitude)

    assert grid["lon_axis"].tolist() == [100.0, 100.01]
    assert grid["lat_axis"].tolist() == [30.0, 30.01]
    # sorted by (latitude index, longitude index)
    assert grid["gy"].tolist() == [0, 0, 1, 1]
    assert grid["gx"].tolist() == [0, 1, 0, 1]


def test_quantize_values_respects_the_documented_error_bound():
    values = np.array([
        [0.0, 500.0, 1000.0],
        [3.0, 3.5, 4.0],
        [10.0, 10.0, 10.5],
        [0.0, 0.5, 1.0],
        [2.0, 2.5, 2.0],
        [5.0, 5.5, 6.0],
    ])

    quantised, minimums, maximums = quantize_values(values)
    restored = minimums[:, None] + quantised.astype(float) * ((maximums - minimums) / 65535)[:, None]

    assert quantised.dtype == np.uint16
    assert np.allclose(restored, values, atol=(maximums - minimums).max() / 65535 / 2 + 1e-9)
    # constant columns cannot be quantised meaningfully
    with pytest.raises(BuildError, match="must vary"):
        quantize_values(np.zeros((6, 4)))


def test_encode_decode_points_round_trips():
    longitude = np.array([100.0, 100.01, 100.0, 100.01])
    latitude = np.array([30.0, 30.0, 30.01, 30.01])
    values = np.array([
        [1.0, 2.0, 3.0, 4.0],
        [1.0, 2.0, 3.0, 4.5],
        [1.0, 2.0, 3.0, 4.0],
        [1.0, 2.0, 3.5, 4.0],
        [1.0, 2.0, 3.0, 4.0],
        [1.0, 2.5, 3.0, 4.0],
    ])
    grid = build_grid(longitude, latitude)
    ordered = values[:, grid["order"]]
    quantised, minimums, maximums = quantize_values(ordered)

    blob = encode_points(
        point_count=grid["gx"].size,
        class_values=np.array([1, 2, 3, 1], dtype=np.uint8),
        gx=grid["gx"],
        gy=grid["gy"],
        quantised=quantised,
        lon_axis=grid["lon_axis"],
        lat_axis=grid["lat_axis"],
        minimums=minimums,
        maximums=maximums,
    )

    assert blob[:4] == MAGIC
    decoded = decode_points(blob)
    assert decoded["pointCount"] == 4
    assert decoded["lonAxis"].tolist() == pytest.approx([100.0, 100.01])
    assert decoded["latAxis"].tolist() == pytest.approx([30.0, 30.01])
    assert decoded["gx"].tolist() == [0, 1, 0, 1]
    assert decoded["gy"].tolist() == [0, 0, 1, 1]
    assert decoded["class"].tolist() == [1, 2, 3, 1]
    assert np.allclose(decoded["values"], ordered, atol=1e-3)


def test_binary_offsets_match_the_encoded_length():
    offsets = binary_offsets(point_count=5, lon_count=3, lat_count=2, column_count=6)
    expected = 120 + 8 * 3 + 8 * 2 + 2 * 5 + 2 * 5 + 2 * 5 * 6 + 5
    assert offsets["total"] == expected


def test_decode_points_rejects_a_truncated_transport():
    import struct

    header = bytearray(120)
    struct.pack_into("<4sHHIIII", header, 0, MAGIC, 1, 0, 5, 3, 2, 6)
    with pytest.raises(BuildError, match="length does not match"):
        decode_points(bytes(header))


def test_build_water_demand_data_writes_deterministic_artifacts(tmp_path):
    workbook = write_workbook(tmp_path / "values.xlsx", sample_rows(size=12))
    outline_path = tmp_path / "outline.json"
    outline_path.write_text(json.dumps({"type": "Polygon", "coordinates": square_geometry()["coordinates"]}), encoding="utf-8")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(builder, "read_region_geometry", lambda _path: square_geometry())
    monkeypatch.setattr(builder, "read_region_name", lambda _path: "半干旱区")
    region_path = tmp_path / "region.shp"
    region_path.write_bytes(b"stub")
    try:
        manifest = builder.build_water_demand_data(
            workbook,
            region_path,
            outline_path,
            tmp_path / "out",
            force=True,
        )
    finally:
        monkeypatch.undo()

    output = tmp_path / "out"
    assert manifest["schemaVersion"] == 1
    assert manifest["pointCount"] == 144
    assert manifest["unit"] == "mm"
    assert manifest["regions"][0]["name"] == "半干旱区"
    assert manifest["pointsInsideRegion"] == 144

    raw = (output / "points.bin").read_bytes()
    assert gzip.decompress((output / "points.bin.gz").read_bytes()) == raw
    decoded = decode_points(raw)
    assert decoded["pointCount"] == 144

    overview = json.loads((output / "overview.json").read_text(encoding="utf-8"))
    assert gzip.decompress((output / "overview.json.gz").read_bytes()) == (output / "overview.json").read_bytes()
    assert overview["legend"][0]["label"] == "立即补水"
    assert [metric["label"] for metric in overview["metrics"]] == ["生态耗水", "生态需水", "生态补水"]
    assert overview["regions"]["features"][0]["properties"]["bounds"][0][0] == pytest.approx(29.0)
