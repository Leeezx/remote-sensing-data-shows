"""Tests for spatial query endpoints (point and area)."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


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
