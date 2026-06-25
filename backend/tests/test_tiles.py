"""Tests for the tile serving endpoint."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_tile_not_found():
    """GET /data/tiles/... returns 404 when tile does not exist."""
    response = client.get("/data/tiles/ndvi/2025-06/5/12/12.png")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_tile_invalid_layer():
    """GET /data/tiles/... with an invalid layer returns 404."""
    response = client.get("/data/tiles/unknown/2025-06/5/12/12.png")
    assert response.status_code == 404
