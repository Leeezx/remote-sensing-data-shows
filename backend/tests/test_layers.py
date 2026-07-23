"""Tests for layer listing and time point endpoints."""

import json
from copy import deepcopy
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from data import validate_data
from backend import et_legends
from backend.et_legends import ETLegendUnavailableError
from backend.main import app
from backend.routers import layers as layers_router
from backend.external_rasters import RasterSource

client = TestClient(app)


def test_get_layers():
    """GET /api/layers returns the configured real-data layers only."""
    response = client.get("/api/layers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    ids = {layer["id"] for layer in data}
    assert ids == {"ssm", "et", "sm_10cm", "sm_30cm", "sm_60cm", "sm_100cm"}
    assert not ids.intersection({"ndvi", "precipitation", "soil_moisture", "lst"})


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


def test_removed_layer_times_returns_404():
    """Removed example layers are no longer exposed by the API."""
    response = client.get("/api/layers/ndvi/times")
    assert response.status_code == 404


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
    monkeypatch.setattr(layers_router, "RASTER_ROOT", tmp_path / "data" / "rasters")
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
    monkeypatch.setattr(layers_router, "RASTER_ROOT", tmp_path / "data" / "rasters")
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
    monkeypatch.setattr(layers_router, "RASTER_ROOT", tmp_path / "data" / "rasters")
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
    monkeypatch.setattr(layers_router, "RASTER_ROOT", tmp_path / "data" / "rasters")
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
    monkeypatch.setattr(layers_router, "RASTER_ROOT", tmp_path / "data" / "rasters")
    monkeypatch.setattr(
        layers_router,
        "get_layer",
        lambda layer_id: metadata_calls.append(layer_id),
    )

    response = client.get("/api/layers/ssm/legend", params={"time": "../secret_01"})

    assert response.status_code == 422
    assert "Invalid SSM time" in response.json()["detail"]
    assert metadata_calls == []


def test_get_et_legend_uses_precomputed_time_entry(monkeypatch, tmp_path):
    et_path = tmp_path / "2010_8day_01_cog.tif"
    et_path.touch()
    dynamic_legend = [
        {"value": 12.3, "color": "#d53e4f", "label": "12.3 mm/8天"}
    ]
    calls = []
    monkeypatch.setattr(
        layers_router,
        "get_layer",
        lambda layer_id: {
            "id": layer_id,
            "unit": "mm/8天",
            "legend": [{"value": 0, "color": "#d53e4f", "label": "低"}],
        },
    )
    monkeypatch.setattr(
        layers_router,
        "resolve_external_raster",
        lambda *_args: RasterSource(et_path, 1),
    )
    monkeypatch.setattr(
        layers_router,
        "get_precomputed_et_legend",
        lambda time: calls.append(time) or dynamic_legend,
    )

    response = client.get("/api/layers/et/legend", params={"time": "2010-01-01"})

    assert response.status_code == 200
    assert response.json()["legend"] == dynamic_legend
    assert calls == ["2010-01-01"]


def test_get_et_legend_returns_503_when_precomputed_entry_is_unavailable(
    monkeypatch, tmp_path
):
    et_path = tmp_path / "2010_8day_01_cog.tif"
    et_path.touch()
    monkeypatch.setattr(
        layers_router,
        "get_layer",
        lambda layer_id: {
            "id": layer_id,
            "unit": "mm/8天",
            "legend": [{"value": 0, "color": "#d53e4f", "label": "低"}],
        },
    )
    monkeypatch.setattr(
        layers_router,
        "resolve_external_raster",
        lambda *_args: RasterSource(et_path, 1),
    )

    def unavailable(_time):
        raise ETLegendUnavailableError("missing test entry")

    monkeypatch.setattr(
        layers_router, "get_precomputed_et_legend", unavailable
    )

    response = client.get("/api/layers/et/legend", params={"time": "2010-01-01"})

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "ET legend is unavailable for time '2010-01-01'"
    )


def test_get_et_legend_keeps_missing_period_404_before_legend_lookup(
    monkeypatch,
):
    legend_calls = []

    def missing_period(*_args):
        raise FileNotFoundError("missing period")

    monkeypatch.setattr(
        layers_router,
        "resolve_external_raster",
        missing_period,
    )
    monkeypatch.setattr(
        layers_router,
        "get_precomputed_et_legend",
        lambda time: legend_calls.append(time),
    )

    response = client.get("/api/layers/et/legend", params={"time": "2010-01-01"})

    assert response.status_code == 404
    assert response.json()["detail"] == "missing period"
    assert legend_calls == []


@pytest.mark.parametrize("persisted_contents", [None, "{bad json"])
def test_get_et_legend_returns_safe_503_for_missing_or_bad_json(
    monkeypatch, tmp_path, persisted_contents
):
    et_path = tmp_path / "2010_8day_01_cog.tif"
    et_path.touch()
    legend_path = tmp_path / "et_legends.json"
    if persisted_contents is not None:
        legend_path.write_text(persisted_contents, encoding="utf-8")
    monkeypatch.setattr(et_legends, "ET_LEGEND_CACHE_PATH", legend_path)
    monkeypatch.setattr(
        layers_router,
        "resolve_external_raster",
        lambda *_args: RasterSource(et_path, 1),
    )

    response = client.get("/api/layers/et/legend", params={"time": "2010-01-01"})

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "ET legend is unavailable for time '2010-01-01'"
    )
    assert str(legend_path) not in response.text


def test_get_et_legend_does_not_compute_runtime_percentiles(
    monkeypatch, tmp_path
):
    et_path = tmp_path / "2010_8day_01_cog.tif"
    et_path.touch()
    legend_path = tmp_path / "et_legends.json"
    persisted_legend = [
        {
            "value": float(index),
            "color": f"#{index:06x}",
            "label": f"{index:.1f} mm/8天",
        }
        for index in range(1, 7)
    ]
    legend_path.write_text(
        json.dumps(
            {
                "version": 1,
                "legends": {"2010-01-01": persisted_legend},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(et_legends, "ET_LEGEND_CACHE_PATH", legend_path)
    monkeypatch.setattr(
        layers_router,
        "resolve_external_raster",
        lambda *_args: RasterSource(et_path, 1),
    )
    monkeypatch.setattr(
        et_legends,
        "np",
        SimpleNamespace(
            percentile=lambda *_args, **_kwargs: pytest.fail(
                "runtime percentile calculation is forbidden"
            )
        ),
    )

    response = client.get("/api/layers/et/legend", params={"time": "2010-01-01"})

    assert response.status_code == 200
    assert response.json()["legend"] == persisted_legend


def test_et_metadata_describes_single_period_cogs():
    layer = next(item for item in client.get("/api/layers").json() if item["id"] == "et")

    assert "single-band" in layer["description"]
    assert "per 8-day period" in layer["description"]
    assert "annual GeoTIFF" not in layer["description"]
