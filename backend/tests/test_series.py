"""Tests for time series endpoint."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_get_series_full_range():
    """GET /api/series returns all 12 months for a layer."""
    response = client.get("/api/series?layerId=ndvi")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 12
    # Each entry should have time and value
    for entry in data:
        assert "time" in entry
        assert "value" in entry
        assert isinstance(entry["value"], (int, float))


def test_get_series_date_filter():
    """Start/end filter returns a subset of the data."""
    response = client.get("/api/series?layerId=ndvi&start=2025-03&end=2025-06")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Should have 4 entries: 03, 04, 05, 06
    assert len(data) == 4
    times = [entry["time"] for entry in data]
    assert times == ["2025-03", "2025-04", "2025-05", "2025-06"]


def test_get_series_invalid_layer():
    """Unknown layer returns 404."""
    response = client.get("/api/series?layerId=unknown_layer")
    assert response.status_code == 404
