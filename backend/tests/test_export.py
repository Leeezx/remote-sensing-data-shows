"""Tests for CSV export endpoint."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def _login_as_researcher() -> str:
    """Helper: login as researcher and return the access token."""
    resp = client.post(
        "/api/auth/login",
        json={"username": "researcher", "password": "researcher123"},
    )
    return resp.json()["access_token"]


def _login_as_viewer() -> str:
    """Helper: login as viewer and return the access token."""
    resp = client.post(
        "/api/auth/login",
        json={"username": "viewer", "password": "viewer123"},
    )
    return resp.json()["access_token"]


def test_export_csv_as_researcher():
    """Researcher can export CSV and gets correct Content-Type."""
    token = _login_as_researcher()
    response = client.get(
        "/api/export/csv?layerId=ndvi",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")


def test_export_csv_as_viewer():
    """Viewer accessing export CSV returns 403."""
    token = _login_as_viewer()
    response = client.get(
        "/api/export/csv?layerId=ndvi",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_export_csv_no_auth():
    """No auth returns 401."""
    response = client.get("/api/export/csv?layerId=ndvi")
    assert response.status_code == 401


def test_export_csv_content():
    """CSV has correct header and data rows."""
    token = _login_as_researcher()
    response = client.get(
        "/api/export/csv?layerId=ndvi&start=2025-01&end=2025-03",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    text = response.text
    lines = text.strip().split("\r\n") if "\r\n" in text else text.strip().split("\n")
    # Header should be "time,value"
    assert lines[0] == "time,value"
    # Should have header + 3 data rows = 4 lines
    assert len(lines) == 4
    # Check first data row format
    assert lines[1].startswith("2025-01,")
