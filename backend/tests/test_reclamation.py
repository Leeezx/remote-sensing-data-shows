"""Tests for reclamation map artifact endpoints."""

import gzip
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import reclamation as reclamation_router


client = TestClient(app)


@pytest.fixture
def artifact_root(tmp_path):
    overview = {"schemaVersion": 1, "regions": [{"id": "A"}]}
    points = {"schemaVersion": 1, "region": {"id": "A"}, "points": []}
    (tmp_path / "points").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schemaVersion": 1, "regions": [{"id": "A"}]}),
        encoding="utf-8",
    )
    for relative_path, payload in (
        ("overview.json", overview),
        ("points/A.json", points),
    ):
        raw_path = tmp_path / relative_path
        raw_path.write_text(json.dumps(payload), encoding="utf-8")
        with gzip.open(f"{raw_path}.gz", "wt", encoding="utf-8") as gzip_file:
            json.dump(payload, gzip_file)
    return tmp_path


def test_reclamation_overview_and_points_prefer_gzip(monkeypatch, artifact_root):
    monkeypatch.setattr(reclamation_router, "RECLAMATION_ROOT", artifact_root)

    overview = client.get("/api/reclamation/regions", headers={"Accept-Encoding": "identity"})
    points = client.get("/api/reclamation/points/A", headers={"Accept-Encoding": "gzip"})

    assert overview.status_code == 200
    assert overview.json()["schemaVersion"] == 1
    assert overview.headers["cache-control"] == "public, max-age=300"
    assert points.status_code == 200
    assert points.json()["region"]["id"] == "A"
    assert points.headers["content-encoding"] == "gzip"
    assert points.headers["vary"] == "Accept-Encoding"
    assert points.headers["cache-control"] == "public, max-age=86400"
    assert points.headers["etag"]


def test_reclamation_respects_a_zero_gzip_quality_value(monkeypatch, artifact_root):
    monkeypatch.setattr(reclamation_router, "RECLAMATION_ROOT", artifact_root)

    response = client.get(
        "/api/reclamation/regions",
        headers={"Accept-Encoding": "br, gzip;q=0, identity;q=1"},
    )

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.headers["vary"] == "Accept-Encoding"
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.headers["etag"]


def test_reclamation_points_reject_unknown_and_corrupt_artifacts(monkeypatch, artifact_root):
    monkeypatch.setattr(reclamation_router, "RECLAMATION_ROOT", artifact_root)

    assert client.get("/api/reclamation/points/../../secret").status_code == 404
    assert client.get("/api/reclamation/points/UNKNOWN").status_code == 404
    (artifact_root / "manifest.json").write_text("{broken", encoding="utf-8")
    assert client.get("/api/reclamation/regions").status_code == 500
