"""Tests for layer listing and time point endpoints."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_get_layers():
    """GET /api/layers returns 4 layers."""
    response = client.get("/api/layers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 4


def test_layer_fields():
    """Each layer has all required fields."""
    response = client.get("/api/layers")
    data = response.json()
    required_fields = {"id", "name", "type", "unit", "timeRange", "tileTemplate", "legend"}
    for layer in data:
        assert required_fields.issubset(layer.keys()), f"Layer {layer.get('id')} missing fields"


def test_get_layer_times():
    """GET /api/layers/{layerId}/times returns 12 monthly timestamps."""
    response = client.get("/api/layers/ndvi/times")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 12
    assert data[0] == "2025-01"
    assert data[-1] == "2025-12"


def test_get_layer_times_invalid_layer():
    """Unknown layer returns 404."""
    response = client.get("/api/layers/unknown_layer/times")
    assert response.status_code == 404
