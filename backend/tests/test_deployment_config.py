from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-acr.yml"


def publish_workflow_text():
    return PUBLISH_WORKFLOW.read_text(encoding="utf-8")


def compose():
    return yaml.safe_load(
        (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )


def nginx_location_block(nginx: str, declaration: str) -> str:
    marker = f"location {declaration} {{"
    start = nginx.index(marker)
    end = nginx.index("\n    }", start)
    return nginx[start:end]


def test_only_caddy_publishes_host_ports():
    services = compose()["services"]
    assert services["edge"]["ports"] == ["80:80", "443:443"]
    assert "ports" not in services["frontend"]
    assert "ports" not in services["backend"]


def test_edge_healthcheck_does_not_depend_on_the_site_hostname():
    edge = compose()["services"]["edge"]
    assert edge["healthcheck"]["test"] == [
        "CMD",
        "caddy",
        "validate",
        "--config",
        "/etc/caddy/Caddyfile",
        "--adapter",
        "caddyfile",
    ]


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
    assert environment["IRRIGATION_RUNTIME_STATS_ROOT"] == (
        "/app/runtime-data/stats/irrigation_runtime"
    )
    assert environment["UVICORN_WORKERS"] == "${UVICORN_WORKERS:-2}"
    assert environment["GDAL_CACHEMAX"] == "${GDAL_CACHEMAX:-256}"
    assert environment["MAX_AREA_QUERY_PIXELS"] == (
        "${MAX_AREA_QUERY_PIXELS:-4000000}"
    )
    assert backend["healthcheck"]["start_period"] == "120s"
    assert "/api/ready" in " ".join(backend["healthcheck"]["test"])

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    deployment_guide = (ROOT / "docs" / "deployment.md").read_text(
        encoding="utf-8"
    )
    assert "UVICORN_WORKERS=2" in env_example
    assert (
        "IRRIGATION_RUNTIME_STATS_ROOT="
        "data/stats/irrigation_runtime"
    ) in env_example
    assert "--workers ${UVICORN_WORKERS:-2}" in dockerfile
    assert "UVICORN_WORKERS=2" in deployment_guide
    for guide in (
        (ROOT / "README.md").read_text(encoding="utf-8"),
        deployment_guide,
    ):
        assert "python scripts/build_irrigation_runtime_stats.py" in guide
        assert "data/stats/irrigation_runtime/" in guide


def test_proxy_contract_contains_limits_cache_and_internal_port():
    nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")
    assert "listen 8080" in nginx
    assert "limit_req_zone" in nginx
    assert "limit_conn_zone" in nginx
    assert (
        "proxy_cache_path /tmp/nginx-cache levels=1:2 "
        "keys_zone=tile_cache:32m max_size=8g inactive=14d "
        "use_temp_path=off;"
    ) in nginx
    for declaration in (
        "/cog/",
        "~ ^/data/(?:ssm|raster|irrigation)-tiles/",
    ):
        block = nginx_location_block(nginx, declaration)
        assert "proxy_cache tile_cache;" in block
        assert "proxy_cache_methods GET HEAD;" in block
        assert 'proxy_cache_key "$scheme$proxy_host$request_uri";' in block
        assert "proxy_cache_valid 200 24h;" in block
        assert "proxy_cache_lock on;" in block
        assert "proxy_cache_lock_timeout 60s;" in block
        assert "proxy_cache_lock_age 60s;" in block
        assert "proxy_cache_background_update on;" in block
        assert (
            "proxy_cache_use_stale error timeout updating "
            "http_500 http_502 http_503 http_504;"
        ) in block
    assert "map $status $tile_browser_cache_control" in nginx
    assert '200 "public, max-age=3600";' in nginx
    assert 'default "no-store";' in nginx
    assert (
        nginx.count(
            "add_header Cache-Control $tile_browser_cache_control always;"
        )
        == 2
    )
    assert (
        nginx.count(
            "add_header X-Tile-Cache $upstream_cache_status always;"
        )
        == 2
    )
    for header in (
        'add_header X-Frame-Options "SAMEORIGIN" always;',
        'add_header X-Content-Type-Options "nosniff" always;',
        'add_header Referrer-Policy "strict-origin-when-cross-origin" always;',
    ):
        assert nginx.count(header) == 5
    assert "location = /api/query/area" in nginx
    assert "real_ip_header X-Forwarded-For" in nginx
    assert "proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto" in nginx
    assert "proxy_set_header X-Forwarded-Proto $scheme" not in nginx


def test_proxy_caches_irrigation_statistics_by_full_uri():
    nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")
    for endpoint in (
        "/api/irrigation/regions/averages",
        "/api/irrigation/series",
    ):
        block = nginx_location_block(nginx, f"= {endpoint}")
        assert "proxy_cache tile_cache;" in block
        assert "proxy_cache_methods GET HEAD;" in block
        assert 'proxy_cache_key "$scheme$proxy_host$request_uri";' in block
        assert "proxy_cache_valid 200 1h;" in block
        assert "proxy_cache_lock on;" in block
        assert (
            "add_header X-Stats-Cache $upstream_cache_status always;"
            in block
        )
        for header in (
            'add_header X-Frame-Options "SAMEORIGIN" always;',
            'add_header X-Content-Type-Options "nosniff" always;',
            (
                'add_header Referrer-Policy '
                '"strict-origin-when-cross-origin" always;'
            ),
        ):
            assert header in block


def test_runtime_images_are_versioned_and_unprivileged():
    backend = (ROOT / "Dockerfile.backend").read_text(encoding="utf-8")
    frontend = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    assert "FROM python:3.12-slim-bookworm" in backend
    assert "USER app" in backend
    assert "FROM nginxinc/nginx-unprivileged:1.28-alpine" in frontend
    assert "RUN mkdir -p /tmp/nginx-cache" in frontend


def test_frontend_uses_persistent_tile_cache_volume():
    config = compose()
    frontend_volumes = config["services"]["frontend"]["volumes"]

    assert {
        "type": "volume",
        "source": "nginx_tile_cache",
        "target": "/tmp/nginx-cache",
    } in frontend_volumes
    assert "nginx_tile_cache" in config["volumes"]


def test_caddy_site_address_is_environment_driven():
    assert (ROOT / "Caddyfile").read_text(encoding="utf-8").splitlines()[0] == (
        "{$SITE_ADDRESS} {"
    )


def test_runtime_requirements_exclude_test_and_removed_auth_packages():
    runtime = (ROOT / "backend" / "requirements.txt").read_text(
        encoding="utf-8"
    )
    for removed in ("pytest", "httpx", "PyJWT", "bcrypt", "python-multipart"):
        assert removed not in runtime
    for direct in ("numpy==", "rasterio==", "pyproj==", "rio-tiler=="):
        assert direct in runtime


def test_ci_does_not_build_docker_images():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "pytest backend/tests/" in workflow
    assert "npm run build" in workflow
    assert "docker build" not in workflow
    assert "docker compose build" not in workflow


def test_acr_publish_workflow_is_manual_only_and_uses_secrets():
    workflow = yaml.safe_load(publish_workflow_text())
    assert set(workflow["on"]) == {"workflow_dispatch"}

    text = publish_workflow_text()
    for secret in (
        "ACR_REGISTRY",
        "ACR_NAMESPACE",
        "ACR_USERNAME",
        "ACR_PASSWORD",
    ):
        assert f"secrets.{secret}" in text


def test_acr_publish_workflow_publishes_all_runtime_images():
    text = publish_workflow_text()
    assert "--platform linux/amd64" in text
    assert "caddy:2.10-alpine" in text
    for repository in ("backend", "frontend", "edge"):
        assert f"/${{{{ env.ACR_NAMESPACE }}}}/{repository}" in text
    assert "latest" in text
    assert "sha-${GITHUB_SHA::12}" in text
    assert "docker push" in text


def test_server_acr_compose_override_is_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "docker-compose.acr.yml" in gitignore


def test_acr_deployment_guide_uses_override_and_disables_builds():
    guide = (ROOT / "docs" / "deployment-acr.md").read_text(encoding="utf-8")
    assert "docker-compose.acr.yml" in guide
    assert "--no-build" in guide
    assert "IMAGE_TAG=sha-" in guide
    assert "docker login" in guide
    assert "registry-1.docker.io" not in guide


def test_frontend_healthchecks_use_explicit_ipv4_loopback():
    compose_healthcheck = compose()["services"]["frontend"]["healthcheck"]["test"]
    assert compose_healthcheck == [
        "CMD",
        "wget",
        "-qO-",
        "http://127.0.0.1:8080/",
    ]

    dockerfile = (ROOT / "Dockerfile.frontend").read_text(encoding="utf-8")
    assert "wget -qO- http://127.0.0.1:8080/" in dockerfile
    assert "http://localhost:8080/" not in dockerfile
