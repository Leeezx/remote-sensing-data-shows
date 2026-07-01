"""Tests for spatial query endpoints (point and area)."""

import numpy as np
import pytest
from fastapi import HTTPException

from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import query

client = TestClient(app)

INVALID_SSM_TIMES = [
    "",
    "../secret_01",
    ".._..",
    "2010_01/../../x",
    "2010-13",
    "2010-02-30",
    "foo_bar",
]


class FakeRaster:
    """Minimal rasterio dataset context for SSM helper tests."""

    def __init__(self, data, nodata=None, source_mask=None):
        self.data = np.asarray(data, dtype=float)
        self.nodata = nodata
        self.crs = "EPSG:4326"
        self.height, self.width = self.data.shape
        if source_mask is None:
            source_mask = np.full(self.data.shape, 255, dtype=np.uint8)
        self.source_mask = np.asarray(source_mask, dtype=np.uint8)
        self.data_window = None
        self.read_windows = []
        self.mask_windows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def index(self, x, y):
        if x == 0 and y == 1:
            return 0, 0
        return self.height - 1, self.width - 1

    def read(self, band, window):
        self.data_window = window
        self.read_windows.append(window)
        rows, cols = window
        return self.data[slice(*rows), slice(*cols)]

    def read_masks(self, band, window):
        assert window == self.data_window
        self.mask_windows.append(window)
        rows, cols = window
        return self.source_mask[slice(*rows), slice(*cols)]


def patch_ssm_raster(monkeypatch, tmp_path, data, nodata=None, source_mask=None):
    cog_path = tmp_path / "test_cog.tif"
    cog_path.touch()
    raster = FakeRaster(data, nodata=nodata, source_mask=source_mask)
    monkeypatch.setattr(query, "_ssm_time_to_cog_path", lambda time: cog_path)
    monkeypatch.setattr(query.rasterio, "open", lambda path: raster)
    return raster


@pytest.mark.parametrize("value", [np.nan, -999.0])
def test_ssm_point_query_rejects_invalid_values(monkeypatch, tmp_path, value):
    patch_ssm_raster(monkeypatch, tmp_path, [[value]])

    with pytest.raises(HTTPException) as exc_info:
        query._query_point_SSM(
            {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No valid data at this point"


def test_ssm_point_query_rejects_declared_nodata(monkeypatch, tmp_path):
    patch_ssm_raster(monkeypatch, tmp_path, [[-32768.0]], nodata=-32768.0)

    with pytest.raises(HTTPException) as exc_info:
        query._query_point_SSM(
            {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No valid data at this point"


def test_ssm_point_query_rejects_finite_masked_pixel(monkeypatch, tmp_path):
    patch_ssm_raster(monkeypatch, tmp_path, [[0.2]], source_mask=[[0]])

    with pytest.raises(HTTPException) as exc_info:
        query._query_point_SSM(
            {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No valid data at this point"


def test_ssm_point_query_rejects_nan_declared_nodata(monkeypatch, tmp_path):
    patch_ssm_raster(monkeypatch, tmp_path, [[np.nan]], nodata=np.nan)

    with pytest.raises(HTTPException) as exc_info:
        query._query_point_SSM(
            {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No valid data at this point"


@pytest.mark.parametrize("time", INVALID_SSM_TIMES)
def test_ssm_point_route_rejects_invalid_time_without_opening_raster(
    monkeypatch, time
):
    calls = []
    monkeypatch.setattr(
        query.rasterio, "open", lambda *_args: calls.append(_args)
    )

    response = client.get(
        "/api/query/point",
        params={"layerId": "ssm", "time": time, "lng": 0, "lat": 0},
    )

    assert response.status_code == 422
    assert "Invalid SSM time" in response.json()["detail"]
    assert calls == []


def test_ssm_area_query_excludes_nan_and_sentinel(monkeypatch, tmp_path):
    patch_ssm_raster(monkeypatch, tmp_path, [[0.2, -999.0], [np.nan, 0.4]])

    result = query._query_area_SSM(
        {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0, 1.0, 1.0
    )

    assert result == pytest.approx({"mean": 0.3, "min": 0.2, "max": 0.4, "count": 2})


def test_ssm_area_query_rejects_all_invalid_values(monkeypatch, tmp_path):
    patch_ssm_raster(monkeypatch, tmp_path, [[np.nan, -999.0]])

    with pytest.raises(HTTPException) as exc_info:
        query._query_area_SSM(
            {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0, 1.0, 1.0
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No valid data in the specified area"


def test_ssm_area_query_excludes_declared_nodata(monkeypatch, tmp_path):
    patch_ssm_raster(
        monkeypatch, tmp_path, [[0.2, -32768.0], [0.4, -32768.0]], nodata=-32768.0
    )

    result = query._query_area_SSM(
        {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0, 1.0, 1.0
    )

    assert result == pytest.approx({"mean": 0.3, "min": 0.2, "max": 0.4, "count": 2})


def test_ssm_area_query_excludes_finite_masked_pixel(monkeypatch, tmp_path):
    patch_ssm_raster(
        monkeypatch,
        tmp_path,
        [[0.2, 0.3], [0.4, 0.5]],
        source_mask=[[255, 0], [255, 255]],
    )

    result = query._query_area_SSM(
        {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0, 1.0, 1.0
    )

    assert result == pytest.approx(
        {"mean": 11 / 30, "min": 0.2, "max": 0.5, "count": 3}
    )


def test_ssm_area_query_excludes_nan_declared_nodata(monkeypatch, tmp_path):
    patch_ssm_raster(
        monkeypatch, tmp_path, [[0.2, np.nan], [0.4, np.nan]], nodata=np.nan
    )

    result = query._query_area_SSM(
        {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0, 1.0, 1.0
    )

    assert result == pytest.approx({"mean": 0.3, "min": 0.2, "max": 0.4, "count": 2})


def test_ssm_area_query_reads_matching_row_chunks_and_aggregates(
    monkeypatch, tmp_path
):
    data = np.vstack(
        [
            np.ones((512, 2)),
            np.full((512, 2), 3.0),
            np.full((1, 2), 5.0),
        ]
    )
    data[511, 1] = -999.0
    data[512, 0] = np.nan
    source_mask = np.full(data.shape, 255, dtype=np.uint8)
    source_mask[512, 1] = 0
    raster = patch_ssm_raster(
        monkeypatch, tmp_path, data, source_mask=source_mask
    )

    result = query._query_area_SSM(
        {"id": "ssm", "unit": "m3/m3"}, "2025_01", 0.0, 0.0, 1.0, 1.0
    )

    expected_windows = [
        ((0, 512), (0, 2)),
        ((512, 1024), (0, 2)),
        ((1024, 1025), (0, 2)),
    ]
    assert raster.read_windows == expected_windows
    assert raster.mask_windows == expected_windows
    assert result == {
        "mean": 4099 / 2047,
        "min": 1.0,
        "max": 5.0,
        "count": 2047,
    }


def test_ssm_area_query_all_invalid_chunks_return_404(monkeypatch, tmp_path):
    raster = patch_ssm_raster(
        monkeypatch, tmp_path, np.full((513, 2), np.nan)
    )

    with pytest.raises(HTTPException) as exc_info:
        query._query_area_SSM(
            {"id": "ssm", "unit": "m3/m3"},
            "2025_01",
            0.0,
            0.0,
            1.0,
            1.0,
        )

    assert raster.read_windows == [((0, 512), (0, 2)), ((512, 513), (0, 2))]
    assert raster.mask_windows == raster.read_windows
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No valid data in the specified area"


@pytest.mark.parametrize("time", INVALID_SSM_TIMES)
def test_ssm_area_route_rejects_invalid_time_without_opening_raster(
    monkeypatch, time
):
    calls = []
    monkeypatch.setattr(
        query.rasterio, "open", lambda *_args: calls.append(_args)
    )

    response = client.post(
        "/api/query/area",
        json={
            "layerId": "ssm",
            "time": time,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
        },
    )

    assert response.status_code == 422
    assert "Invalid SSM time" in response.json()["detail"]
    assert calls == []


def test_point_query_ndvi():
    """Point query at known coordinates returns a value."""
    # Coordinates in North China Plain region
    response = client.get(
        "/api/query/point?layerId=ndvi&time=2025-01&lng=116.4&lat=39.9"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["layerId"] == "ndvi"
    assert data["time"] == "2025-01"
    assert "value" in data
    assert "unit" in data
    assert isinstance(data["value"], (int, float))


def test_point_query_missing_params():
    """Missing required params returns 422."""
    response = client.get("/api/query/point?layerId=ndvi")
    assert response.status_code == 422


def test_point_query_no_data():
    """Coordinates outside any known region returns 404."""
    # Coordinates in the middle of the Pacific Ocean
    response = client.get(
        "/api/query/point?layerId=ndvi&time=2025-01&lng=-150.0&lat=0.0"
    )
    assert response.status_code == 404


def test_area_query_rectangle():
    """Area query with a valid rectangle returns statistics."""
    response = client.post(
        "/api/query/area",
        json={
            "layerId": "ndvi",
            "time": "2025-01",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [116.1, 39.7],
                        [116.7, 39.7],
                        [116.7, 40.1],
                        [116.1, 40.1],
                        [116.1, 39.7],
                    ]
                ],
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    for field in ["mean", "max", "min", "count"]:
        assert field in data, f"Missing field: {field}"


def test_area_query_unknown_region():
    """Area with coordinates outside all regions returns 404."""
    response = client.post(
        "/api/query/area",
        json={
            "layerId": "ndvi",
            "time": "2025-01",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-150.0, -1.0],
                        [-149.0, -1.0],
                        [-149.0, 1.0],
                        [-150.0, 1.0],
                        [-150.0, -1.0],
                    ]
                ],
            },
        },
    )
    assert response.status_code == 404


def test_area_query_invalid_geometry():
    """Malformed geometry returns 422."""
    response = client.post(
        "/api/query/area",
        json={
            "layerId": "ndvi",
            "time": "2025-01",
            "geometry": "not_a_geometry",
        },
    )
    assert response.status_code == 422
