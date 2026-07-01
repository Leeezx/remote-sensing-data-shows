"""Tests for layer listing and time point endpoints."""

from copy import deepcopy

from fastapi.testclient import TestClient

from data import validate_data
from backend.main import app
from backend.routers import layers as layers_router

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


def test_get_ssm_legend_returns_dynamic_legend_with_exact_arguments(monkeypatch, tmp_path):
    cog_path = tmp_path / "data" / "rasters" / "ssm" / "2010_01_cog.tif"
    cog_path.parent.mkdir(parents=True)
    cog_path.touch()
    base_legend = [
        {"value": value, "color": color, "label": f"base {value}"}
        for value, color in zip(
            [0.09, 0.15, 0.22, 0.28, 0.35, 0.40],
            ["#010203", "#111213", "#212223", "#313233", "#414243", "#515253"],
        )
    ]
    dynamic_legend = [{"value": 0.12, "color": "#010203", "label": "0.120 m³/m³"}]
    calls = []
    monkeypatch.setattr(layers_router, "PROJECT_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        layers_router,
        "get_layer",
        lambda layer_id: {
            "id": layer_id,
            "unit": "m³/m³",
            "legend": base_legend,
        },
    )
    monkeypatch.setattr(
        layers_router,
        "get_dynamic_legend",
        lambda path, legend, unit: calls.append((path, legend, unit))
        or dynamic_legend,
        raising=False,
    )

    response = client.get("/api/layers/ssm/legend?time=2010_01")

    assert response.status_code == 200
    assert response.json() == {
        "layerId": "ssm",
        "time": "2010_01",
        "unit": "m³/m³",
        "legend": dynamic_legend,
    }
    assert calls == [(cog_path, base_legend, "m³/m³")]


def test_get_ssm_legend_rejects_invalid_time_without_computation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(layers_router, "PROJECT_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        layers_router,
        "get_dynamic_legend",
        lambda *_args: calls.append(_args),
        raising=False,
    )

    response = client.get("/api/layers/ssm/legend", params={"time": "../secret_01"})

    assert response.status_code == 422
    assert "Invalid SSM time" in response.json()["detail"]
    assert calls == []


def test_get_ssm_legend_reports_missing_cog_without_computation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(layers_router, "PROJECT_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(
        layers_router,
        "get_dynamic_legend",
        lambda *_args: calls.append(_args),
        raising=False,
    )

    response = client.get("/api/layers/ssm/legend?time=2010_01")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "COG file not found for time '2010_01' (looked for: 2010_01_cog.tif)"
    )
    assert calls == []


def test_get_ssm_legend_reports_missing_metadata_without_computation(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(layers_router, "PROJECT_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(layers_router, "get_layer", lambda _layer_id: None)
    monkeypatch.setattr(
        layers_router,
        "get_dynamic_legend",
        lambda *_args: calls.append(_args),
        raising=False,
    )

    response = client.get("/api/layers/ssm/legend?time=2010_01")

    assert response.status_code == 404
    assert response.json()["detail"] == "SSM layer metadata is missing"
    assert calls == []


def test_get_ssm_legend_rejects_invalid_time_before_missing_metadata(
    monkeypatch, tmp_path
):
    metadata_calls = []
    monkeypatch.setattr(layers_router, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        layers_router,
        "get_layer",
        lambda layer_id: metadata_calls.append(layer_id),
    )

    response = client.get("/api/layers/ssm/legend", params={"time": "../secret_01"})

    assert response.status_code == 422
    assert "Invalid SSM time" in response.json()["detail"]
    assert metadata_calls == []
