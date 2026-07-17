"""Tests for irrigation water display endpoints."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend import data_loader
from backend.routers import irrigation as irrigation_router
from backend.shapefile_geojson import _read_dbf_records

client = TestClient(app)


def test_get_irrigation_layer_metadata():
    response = client.get("/api/irrigation/layer")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "irrigation_water"
    assert data["name"] == "灌溉用水量"
    assert data["unit"] == "万m³"
    assert "{time}" in data["tileTemplate"]
    assert data["timeRange"]["step"] == "annual"


def test_get_irrigation_times_for_annual_and_8day_rasters():
    annual = client.get("/api/irrigation/times?resolution=annual")
    monthly = client.get("/api/irrigation/times?resolution=month")

    assert annual.status_code == 200
    assert "2004" in annual.json()
    assert "2024" in annual.json()
    assert "2010" in annual.json()
    assert monthly.status_code == 200
    assert monthly.json()[0].startswith("2010-")


def test_get_irrigation_legend_uses_time_specific_raster(monkeypatch, tmp_path):
    raster_path = tmp_path / "IWU_2024.TIF"
    raster_path.touch()
    legend = [
        {"value": 1, "color": "#111111", "label": "1 万m³"},
        {"value": 2, "color": "#222222", "label": "2 万m³"},
    ]
    calls = []
    monkeypatch.setattr(
        irrigation_router,
        "irrigation_time_to_cog_path",
        lambda annual_root, annual_cog_root, eight_day_root, eight_day_cog_root, time: calls.append(time) or raster_path,
        raising=False,
    )
    monkeypatch.setattr(
        irrigation_router,
        "get_irrigation_dynamic_legend",
        lambda path, base, unit, time="": calls.append((path, base, unit)) or legend,
        raising=False,
    )

    response = client.get("/api/irrigation/legend?time=2024")

    assert response.status_code == 200
    assert response.json() == {
        "layerId": "irrigation_water",
        "time": "2024",
        "unit": "万m³",
        "legend": legend,
    }
    assert calls[0] == "2024"
    assert calls[1][0] == raster_path


def test_irrigation_dynamic_legend_excludes_negative_values():
    import numpy as np

    from backend.irrigation_legend import build_irrigation_dynamic_legend

    base_legend = [
        {"value": 0, "color": "#111111", "label": "0"},
        {"value": 1, "color": "#222222", "label": "1"},
        {"value": 2, "color": "#333333", "label": "2"},
        {"value": 3, "color": "#444444", "label": "3"},
        {"value": 4, "color": "#555555", "label": "4"},
        {"value": 5, "color": "#666666", "label": "5"},
    ]
    values = np.array([[-20, -1, 0, 1, 2, 3, 4, 5]], dtype=float)

    legend = build_irrigation_dynamic_legend(values, base_legend, "万m³")

    assert legend[0]["value"] >= 0
    assert all(item["value"] >= 0 for item in legend)


def test_irrigation_times_scan_configured_raster_directories(monkeypatch, tmp_path):
    annual_dir = tmp_path / "annual"
    monthly_dir = tmp_path / "8day"
    annual_dir.mkdir()
    monthly_dir.mkdir()
    (annual_dir / "IWU_2004.TIF").touch()
    (annual_dir / "IWU_2010.TIF").touch()
    (monthly_dir / "IWU_2010_17.tif").touch()
    (monthly_dir / "IWU_2010_18.tif").touch()
    monkeypatch.setattr(data_loader, "IRRIGATION_ANNUAL_ROOT", annual_dir)
    monkeypatch.setattr(data_loader, "IRRIGATION_8DAY_ROOT", monthly_dir)

    assert data_loader.get_irrigation_times("annual") == ["2004", "2010"]
    assert data_loader.get_irrigation_times("month") == ["2010-05"]


def test_get_irrigation_vectors_reports_county_availability_and_township_chunks(
    monkeypatch,
    tmp_path,
):
    county_path = tmp_path / "county.shp"
    county_path.touch()
    chunk_root = tmp_path / "township_by_county"
    chunk_root.mkdir()
    (chunk_root / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(irrigation_router, "COUNTY_VECTOR_PATH", county_path)
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", chunk_root)

    county = client.get("/api/irrigation/vectors?level=county")
    township = client.get("/api/irrigation/vectors?level=township")

    assert county.status_code == 200
    assert county.json()["level"] == "county"
    assert county.json()["available"] is True
    assert county.json()["url"] == "/api/irrigation/vectors/county"
    assert township.status_code == 200
    assert township.json()["available"] is True
    assert "{countyId}" in township.json()["url"]
    assert "选择县域" in township.json()["message"]


def test_township_vector_requires_county_id():
    response = client.get("/api/irrigation/vectors/township")

    assert response.status_code == 422


def test_township_vector_serves_one_small_cached_county_chunk(monkeypatch, tmp_path):
    chunk_root = tmp_path / "township_by_county"
    chunk_root.mkdir()
    chunk = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": "511011111000",
                    "name": "石子镇",
                    "parentId": "156511011",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[104, 29], [105, 29], [105, 30], [104, 29]]],
                },
            }
        ],
    }
    chunk_path = chunk_root / "511011.geojson"
    chunk_path.write_text(
        json.dumps(chunk, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", chunk_root)
    monkeypatch.setattr(
        irrigation_router,
        "read_shapefile_geojson",
        lambda _path: (_ for _ in ()).throw(AssertionError("must not read nationwide shp")),
    )

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156511011"},
    )

    assert response.status_code == 200
    assert response.json() == chunk
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert int(response.headers["x-chunk-bytes"]) < 1_000_000
    assert response.headers["x-feature-count"] == "1"


def test_township_vector_rejects_invalid_county_id(monkeypatch, tmp_path):
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "../../all"},
    )

    assert response.status_code == 422


def test_county_vector_geojson_uses_configured_shapefile(monkeypatch, tmp_path):
    shp_path = tmp_path / "county.shp"
    shp_path.touch()
    monkeypatch.setattr(irrigation_router, "COUNTY_VECTOR_PATH", shp_path)
    monkeypatch.setattr(
        irrigation_router,
        "read_shapefile_geojson",
        lambda path: {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"id": "1001", "name": "测试县"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[100, 30], [101, 30], [101, 31], [100, 30]]],
                    },
                }
            ],
        },
    )

    response = client.get("/api/irrigation/vectors/county")

    assert response.status_code == 200
    assert response.json()["features"][0]["properties"]["name"] == "测试县"


def test_dbf_reader_strips_null_padding_from_utf8_values(tmp_path):
    dbf_path = tmp_path / "county.dbf"
    dbf_path.with_suffix(".cpg").write_text("UTF-8", encoding="ascii")
    header_length = 65
    record_length = 11
    header = bytearray(32)
    header[0] = 0x03
    header[4:8] = (1).to_bytes(4, "little")
    header[8:10] = header_length.to_bytes(2, "little")
    header[10:12] = record_length.to_bytes(2, "little")
    field = bytearray(32)
    field[:4] = b"name"
    field[11] = ord("C")
    field[16] = 10
    value = "测试".encode("utf-8")
    record = b" " + value + b"\0" * (10 - len(value))
    dbf_path.write_bytes(bytes(header) + bytes(field) + b"\r" + record + b"\x1a")

    records = _read_dbf_records(dbf_path)

    assert records == [{"name": "测试"}]


def test_get_irrigation_regions_filters_by_level():
    response = client.get("/api/irrigation/regions?level=county")

    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert all(region["level"] == "county" for region in data)
    ids = [region["id"] for region in data]
    assert "county_a" in ids


def test_irrigation_region_catalog_contains_both_supported_levels():
    county = client.get("/api/irrigation/regions?level=county")
    township = client.get("/api/irrigation/regions?level=township")

    assert county.status_code == 200
    assert township.status_code == 200
    assert len(county.json()) > 0
    assert len(township.json()) > 0
    assert {item["level"] for item in county.json()} == {"county"}
    assert {item["level"] for item in township.json()} == {"township"}


def test_get_irrigation_series_returns_precomputed_monthly_county_values():
    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "county",
            "regionId": "county_a",
            "period": "monthly",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["region"]["id"] == "county_a"
    assert data["period"] == "monthly"
    assert data["unit"] == "万m³"
    assert data["series"][0] == {"time": "2023-01", "value": 118.4}
    assert data["summary"]["total"] == 1532.2


def test_get_irrigation_series_returns_precomputed_annual_township_values():
    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "township",
            "regionId": "village_a1",
            "period": "annual",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["region"]["id"] == "village_a1"
    assert data["region"]["level"] == "township"
    assert data["period"] == "annual"
    assert data["series"] == [
        {"time": "2021", "value": 328.4},
        {"time": "2022", "value": 346.5},
        {"time": "2023", "value": 358.8},
    ]


def test_get_irrigation_series_returns_404_for_unknown_precomputed_region():
    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "county",
            "regionId": "nonexistent_county_99999",
            "period": "annual",
        },
    )

    assert response.status_code == 404
    assert "not found in precomputed irrigation statistics" in response.json()["detail"]


def test_get_irrigation_series_returns_404_when_period_is_missing(monkeypatch):
    monkeypatch.setattr(
        irrigation_router,
        "get_irrigation_region_series",
        lambda: {
            "unit": "万m³",
            "county": {"county_without_month": {"annual": []}},
            "township": {},
        },
    )

    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "county",
            "regionId": "county_without_month",
            "period": "monthly",
        },
    )

    assert response.status_code == 404
    assert "monthly" in response.json()["detail"]


def test_get_irrigation_series_rejects_mismatched_region_level():
    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "township",
            "regionId": "county_a",
            "period": "annual",
        },
    )

    assert response.status_code == 404


def test_get_irrigation_region_averages_returns_legend_and_averages():
    response = client.get("/api/irrigation/regions/averages?level=county")

    assert response.status_code == 200
    data = response.json()
    assert data["level"] == "county"
    assert data["unit"] == "万m³"
    assert isinstance(data["averages"], list)
    assert len(data["averages"]) > 0
    assert isinstance(data["legend"], list)
    assert len(data["legend"]) == 6
    for item in data["averages"]:
        assert "regionId" in item
        assert "name" in item
        assert "average" in item
    for item in data["legend"]:
        assert "value" in item
        assert "color" in item
        assert "label" in item


def test_get_irrigation_region_averages_legend_has_six_stops():
    response = client.get("/api/irrigation/regions/averages?level=county")

    assert response.status_code == 200
    data = response.json()
    legend = data["legend"]
    assert len(legend) == 6
    # values must be strictly increasing
    values = [item["value"] for item in legend]
    assert all(values[i] < values[i + 1] for i in range(len(values) - 1))
    # colors must be valid hex
    import re
    hex_color = re.compile(r"^#[0-9a-fA-F]{6}$")
    for item in legend:
        assert hex_color.fullmatch(item["color"])


def test_get_irrigation_region_averages_bad_level():
    response = client.get("/api/irrigation/regions/averages?level=province")
    # Literal type validation should reject non-county/non-township
    assert response.status_code == 422


def test_get_township_region_averages_requires_county_id():
    response = client.get("/api/irrigation/regions/averages?level=township")

    assert response.status_code == 422
