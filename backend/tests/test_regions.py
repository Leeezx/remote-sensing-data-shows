"""Tests for the /api/regions endpoint."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_get_regions():
    """GET /api/regions returns a list of regions."""
    response = client.get("/api/regions")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 4
    for region in data:
        assert "id" in region
        assert "name" in region
        assert "bounds" in region
        assert all(k in region["bounds"] for k in ("north", "south", "east", "west"))


def test_region_ids():
    """GET /api/regions returns the expected region ids."""
    response = client.get("/api/regions")
    data = response.json()
    ids = {r["id"] for r in data}
    assert ids == {"north_china", "yangtze_delta", "sichuan_basin", "northeast_plain"}
