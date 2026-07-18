from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def compose():
    return yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )


def test_only_caddy_publishes_host_ports():
    services = compose()["services"]
    assert services["edge"]["ports"] == ["80:80", "443:443"]
    assert "ports" not in services["frontend"]
    assert "ports" not in services["backend"]


def test_backend_runtime_mounts_and_defaults_are_safe():
    backend = compose()["services"]["backend"]
    volumes = backend["volumes"]
    assert any(
        item["target"] == "/app/runtime-data/stats" and item["read_only"]
        for item in volumes
        if isinstance(item, dict)
    )
    assert any(
        item["target"] == "/app/cache"
        for item in volumes
        if isinstance(item, dict)
    )
    bind_mounts = [
        item
        for item in volumes
        if isinstance(item, dict) and item.get("type") == "bind"
    ]
    assert all(
        item["bind"]["create_host_path"] is False for item in bind_mounts
    )
    environment = backend["environment"]
    assert environment["UVICORN_WORKERS"] == "${UVICORN_WORKERS:-1}"
    assert environment["GDAL_CACHEMAX"] == "${GDAL_CACHEMAX:-256}"
    assert environment["MAX_AREA_QUERY_PIXELS"] == (
        "${MAX_AREA_QUERY_PIXELS:-4000000}"
    )
    assert backend["healthcheck"]["start_period"] == "120s"
    assert "/api/ready" in " ".join(backend["healthcheck"]["test"])


def test_proxy_contract_contains_limits_cache_and_internal_port():
    nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")
    assert "listen 8080" in nginx
    assert "limit_req_zone" in nginx
    assert "limit_conn_zone" in nginx
    assert "proxy_cache_valid 200 7d" in nginx
    assert "location = /api/query/area" in nginx
    assert "real_ip_header X-Forwarded-For" in nginx


def test_runtime_images_are_versioned_and_unprivileged():
    backend = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    frontend = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim-bookworm" in backend
    assert "USER app" in backend
    assert "FROM nginxinc/nginx-unprivileged:1.28-alpine" in frontend


def test_caddy_site_address_is_environment_driven():
    assert (ROOT / "Caddyfile").read_text(encoding="utf-8").splitlines()[0] == (
        "{$SITE_ADDRESS} {"
    )
