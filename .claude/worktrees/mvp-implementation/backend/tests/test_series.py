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


def test_get_series_with_region():
    """RegionId parameter returns per-region time series data."""
    # Northeast Plain has distinct winter values (Jan NDVI ~0.10)
    response = client.get("/api/series?layerId=ndvi&regionId=northeast_plain")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 12

    # January NDVI in Northeast Plain should be very low (~0.10)
    jan_entry = next(e for e in data if e["time"] == "2025-01")
    assert jan_entry["value"] == 0.10

    # Verify it's different from the default (North China) series
    response_default = client.get("/api/series?layerId=ndvi")
    default_data = response_default.json()
    default_jan = next(e for e in default_data if e["time"] == "2025-01")
    assert default_jan["value"] == 0.22
    assert jan_entry["value"] != default_jan["value"]


def test_get_series_unknown_region():
    """Unknown regionId falls back to default series."""
    response = client.get("/api/series?layerId=ndvi&regionId=unknown_region")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 12
    # Should return default (North China) data
    jan_entry = next(e for e in data if e["time"] == "2025-01")
    assert jan_entry["value"] == 0.22
