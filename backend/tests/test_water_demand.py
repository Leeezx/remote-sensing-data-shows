"""Tests for water-demand map artifact endpoints."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import water_demand as water_demand_router


client = TestClient(app)
OVERVIEW = {"schemaVersion": 1, "unit": "mm", "regions": {"type": "FeatureCollection", "features": []}}
POINTS = b"WDPT" + bytes(range(64))


@pytest.fixture
def artifact_root(tmp_path):
    manifest = {"schemaVersion": 1, "pointCount": 4}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "overview.json").write_text(json.dumps(OVERVIEW), encoding="utf-8")
    with gzip.open(tmp_path / "overview.json.gz", "wb") as gzip_file:
        gzip_file.write((tmp_path / "overview.json").read_bytes())
    (tmp_path / "points.bin").write_bytes(POINTS)
    with gzip.open(tmp_path / "points.bin.gz", "wb") as gzip_file:
        gzip_file.write(POINTS)
    return tmp_path


def test_overview_and_points_prefer_gzip(monkeypatch, artifact_root):
    monkeypatch.setattr(water_demand_router, "WATER_DEMAND_ROOT", artifact_root)

    overview = client.get("/api/water-demand/overview", headers={"Accept-Encoding": "identity"})
    points = client.get("/api/water-demand/points", headers={"Accept-Encoding": "gzip"})

    assert overview.status_code == 200
    assert overview.headers["cache-control"] == "public, max-age=300"
    assert overview.headers["vary"] == "Accept-Encoding"
    assert overview.json() == OVERVIEW

    assert points.status_code == 200
    assert points.headers["cache-control"] == "public, max-age=86400"
    assert points.headers["content-encoding"] == "gzip"
    # httpx transparently decodes the gzip representation for the test client
    assert points.headers["content-type"] == "application/octet-stream"
    assert points.content == POINTS


def test_points_serves_raw_binary_when_gzip_is_not_accepted(monkeypatch, artifact_root):
    monkeypatch.setattr(water_demand_router, "WATER_DEMAND_ROOT", artifact_root)

    points = client.get("/api/water-demand/points", headers={"Accept-Encoding": "identity"})

    assert points.status_code == 200
    assert "content-encoding" not in points.headers
    assert points.content == POINTS


def test_endpoints_report_missing_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(water_demand_router, "WATER_DEMAND_ROOT", tmp_path)

    response = client.get("/api/water-demand/overview")

    assert response.status_code == 404
    assert response.json()["detail"] == "Water-demand artifacts are unavailable"


def test_endpoints_reject_an_invalid_manifest(monkeypatch, artifact_root):
    (artifact_root / "manifest.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(water_demand_router, "WATER_DEMAND_ROOT", artifact_root)

    response = client.get("/api/water-demand/points")

    assert response.status_code == 500
    assert response.json()["detail"] == "Water-demand artifact manifest is invalid"


def test_endpoints_reject_an_unsupported_schema_version(monkeypatch, artifact_root):
    (artifact_root / "manifest.json").write_text(
        json.dumps({"schemaVersion": 99}), encoding="utf-8"
    )
    monkeypatch.setattr(water_demand_router, "WATER_DEMAND_ROOT", artifact_root)

    response = client.get("/api/water-demand/overview")

    assert response.status_code == 500


def test_endpoints_report_a_missing_point_transport(monkeypatch, artifact_root):
    (artifact_root / "points.bin").unlink()
    (artifact_root / "points.bin.gz").unlink()
    monkeypatch.setattr(water_demand_router, "WATER_DEMAND_ROOT", artifact_root)

    response = client.get("/api/water-demand/points")

    assert response.status_code == 404
    assert response.json()["detail"] == "Water-demand artifact was not found"


def test_endpoints_reject_unknown_gzip_quality(monkeypatch, artifact_root):
    monkeypatch.setattr(water_demand_router, "WATER_DEMAND_ROOT", artifact_root)

    points = client.get("/api/water-demand/points", headers={"Accept-Encoding": "gzip;q=0"})

    assert points.status_code == 200
    assert "content-encoding" not in points.headers
