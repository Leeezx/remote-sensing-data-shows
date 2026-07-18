from fastapi.testclient import TestClient

from backend.main import create_app


def test_api_docs_are_disabled_when_requested():
    client = TestClient(create_app(enable_api_docs=False))
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_app_uses_only_explicit_trimmed_cors_origins():
    client = TestClient(create_app(cors_origins=("https://maps.example",)))
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://maps.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == (
        "https://maps.example"
    )
