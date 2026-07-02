"""Tests for irrigation water display endpoints."""

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


def test_get_irrigation_vectors_reports_county_availability_and_missing_village():
    county = client.get("/api/irrigation/vectors?level=county")
    village = client.get("/api/irrigation/vectors?level=village")

    assert county.status_code == 200
    assert county.json()["level"] == "county"
    assert county.json()["available"] is True
    assert county.json()["url"] == "/api/irrigation/vectors/county"
    assert village.status_code == 200
    assert village.json()["available"] is False
    assert "暂未配置" in village.json()["message"]


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
    assert [region["level"] for region in data] == ["county", "county"]
    assert data[0]["name"] == "示范县A"


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


def test_get_irrigation_series_computes_missing_vector_region(monkeypatch):
    monkeypatch.setattr(
        irrigation_router,
        "find_irrigation_vector_feature",
        lambda level, region_id: {
            "type": "Feature",
            "properties": {"id": region_id, "name": "鄂城区"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[114.8, 30.3], [114.9, 30.3], [114.9, 30.4], [114.8, 30.3]]],
            },
        },
        raising=False,
    )
    monkeypatch.setattr(
        irrigation_router,
        "compute_irrigation_region_series",
        lambda level, region_id, region_name, geometry, period: [
            {"time": "2024", "value": 42.5}
        ],
        raising=False,
    )

    response = client.get(
        "/api/irrigation/series",
        params={"level": "county", "regionId": "156420704", "period": "annual"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["region"] == {
        "id": "156420704",
        "name": "鄂城区",
        "level": "county",
        "parentId": None,
    }
    assert data["series"] == [{"time": "2024", "value": 42.5}]
    assert data["summary"]["total"] == 42.5


def test_get_irrigation_series_rejects_mismatched_region_level():
    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "village",
            "regionId": "county_a",
            "period": "annual",
        },
    )

    assert response.status_code == 404
