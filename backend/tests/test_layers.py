"""Tests for layer listing and time point endpoints."""

from copy import deepcopy

from fastapi.testclient import TestClient

from data import validate_data
from backend.main import app

client = TestClient(app)


def test_get_layers():
    """GET /api/layers returns at least 4 layers."""
    response = client.get("/api/layers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 4


def test_layer_fields():
    """Each layer has all required fields."""
    response = client.get("/api/layers")
    data = response.json()
    required_fields = {"id", "name", "type", "unit", "timeRange", "tileTemplate", "legend"}
    for layer in data:
        assert required_fields.issubset(layer.keys()), f"Layer {layer.get('id')} missing fields"


def test_legend_items_have_numeric_values_and_string_colors():
    """Every legend stop exposes a numeric value and color."""
    response = client.get("/api/layers")
    data = response.json()

    for layer in data:
        for item in layer["legend"]:
            assert isinstance(item.get("value"), (int, float))
            assert not isinstance(item.get("value"), bool)
            assert isinstance(item.get("color"), str)


def test_layer_validation_rejects_non_list_legend(monkeypatch):
    layers, error = validate_data.load_json("data/metadata/layers.json")
    assert error is None
    malformed = deepcopy(layers)
    malformed[0]["legend"] = "not-a-list"
    monkeypatch.setattr(validate_data, "load_json", lambda _path: (malformed, None))

    errors = validate_data.validate_layers()

    assert any("legend must be a list" in error for error in errors)


def test_layer_validation_rejects_non_finite_legend_value(monkeypatch):
    layers, error = validate_data.load_json("data/metadata/layers.json")
    assert error is None
    malformed = deepcopy(layers)
    malformed[0]["legend"][0]["value"] = float("nan")
    monkeypatch.setattr(validate_data, "load_json", lambda _path: (malformed, None))

    errors = validate_data.validate_layers()

    assert any("legend[0].value must be finite" in error for error in errors)


def test_layer_validation_rejects_duplicate_legend_values(monkeypatch):
    layers, error = validate_data.load_json("data/metadata/layers.json")
    assert error is None
    malformed = deepcopy(layers)
    malformed[0]["legend"][1]["value"] = malformed[0]["legend"][0]["value"]
    monkeypatch.setattr(validate_data, "load_json", lambda _path: (malformed, None))

    errors = validate_data.validate_layers()

    assert any("legend values must be unique" in error for error in errors)


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
