"""Tests for authentication endpoints and dependencies."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_login_success_researcher():
    """POST /api/auth/login with correct researcher credentials returns token + user info."""
    response = client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "researcher123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "researcher"
    assert data["user"]["role"] == "researcher"


def test_login_success_viewer():
    """POST /api/auth/login with correct viewer credentials returns token + user info."""
    response = client.post(
        "/api/auth/login",
        json={"username": "viewer", "password": "viewer123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "viewer"
    assert data["user"]["role"] == "viewer"


def test_login_failure():
    """Wrong password returns 401."""
    response = client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "wrong_password"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user():
    """Unknown user returns 401."""
    response = client.post(
        "/api/auth/login",
        json={"username": "nonexistent", "password": "whatever"},
    )
    assert response.status_code == 401


def test_protected_route_no_token():
    """Accessing a protected route without token returns 401."""
    response = client.get("/api/export/csv?layerId=ndvi")
    assert response.status_code == 401


def test_viewer_cannot_export():
    """Viewer accessing export CSV returns 403."""
    # Login as viewer
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "viewer", "password": "viewer123"},
    )
    token = login_resp.json()["access_token"]

    response = client.get(
        "/api/export/csv?layerId=ndvi",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_researcher_can_export():
    """Researcher accessing export CSV returns 200."""
    # Login as researcher
    login_resp = client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "researcher123"},
    )
    token = login_resp.json()["access_token"]

    response = client.get(
        "/api/export/csv?layerId=ndvi",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_invalid_token():
    """Malformed token returns 401."""
    response = client.get(
        "/api/export/csv?layerId=ndvi",
        headers={"Authorization": "Bearer invalid_token_here"},
    )
    assert response.status_code == 401
