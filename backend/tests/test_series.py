"""Tests for time series endpoint."""

from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_removed_layer_series_returns_404():
    response = client.get("/api/series?layerId=ndvi")
    assert response.status_code == 404


def test_get_series_unknown_layer():
    response = client.get("/api/series?layerId=unknown_layer")
    assert response.status_code == 404
