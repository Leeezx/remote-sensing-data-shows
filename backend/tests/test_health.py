from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import health

client = TestClient(app)


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "message" in data


def test_readiness_check_reports_ready(monkeypatch):
    monkeypatch.setattr(health, "collect_readiness_failures", lambda: [])

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": []}


def test_readiness_check_reports_stable_failures(monkeypatch):
    monkeypatch.setattr(
        health, "collect_readiness_failures", lambda: ["county_vector"]
    )

    response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": ["county_vector"],
    }


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "0.1.0"
