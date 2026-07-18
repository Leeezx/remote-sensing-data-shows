# Deployment Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recreate the committed local application on a clean GitHub-ready branch without large generated data, then add a safe single-server deployment path with runtime-data validation, bounded raster queries, and future automatic HTTPS.

**Architecture:** Apply local `main` as one squash-like tree change on top of remote `main`, remove the 218 MiB generated JSON before committing, and keep all large datasets as read-only runtime mounts. Isolate environment parsing, atomic cache publication, and readiness probes in small backend modules; put Caddy in front of an unprivileged Nginx frontend and a non-root single-worker FastAPI backend.

**Tech Stack:** Git, Python 3.12, FastAPI, Rasterio, pytest, React 19, TypeScript, Vite, Vitest, Caddy 2, unprivileged Nginx, Docker Compose, GitHub Actions.

## Global Constraints

- Preserve `E:\遥感数据展示网站` on local branch `main` at `043c3be`; do not reset, clean, stash, or stage its dirty files.
- Perform all work in `E:\遥感数据展示网站\.worktrees\deploy-readiness` on `codex/deploy-readiness`.
- Do not commit `data/stats/irrigation_region_series.json`, `data/rasters/`, generated township chunks, runtime logs, planning state, or test PNGs.
- Do not run Docker build or Docker Compose runtime validation in this plan.
- Use `SITE_ADDRESS=:80`, `UVICORN_WORKERS=1`, `GDAL_CACHEMAX=256`, and `MAX_AREA_QUERY_PIXELS=4000000` as production defaults.
- Keep `/api/health` as liveness and use `/api/ready` for Compose readiness with a 120-second start period.
- Only Caddy may publish host ports; frontend and backend remain internal Compose services.
- Every Python behavior change follows a witnessed RED → GREEN test cycle.
- Open a draft pull request; do not update or force-push remote `main`.

---

### Task 1: Recreate the Local Committed Tree Without the Large Blob

**Files:**
- Modify: `.gitignore`
- Modify: `.dockerignore`
- Remove from tracking: `data/stats/irrigation_region_series.json`
- Preserve: `docs/superpowers/specs/2026-07-18-deployment-readiness-design.md`

**Interfaces:**
- Consumes: committed local branch `main` at `043c3be` and remote baseline `origin/main` at `5d1aeca`.
- Produces: one replacement commit whose tree contains the committed local application but whose history and index contain no generated administrative-series blob.

- [ ] **Step 1: Record immutable safety facts**

Run:

```powershell
git branch --show-current
git rev-parse HEAD
git -C 'E:\遥感数据展示网站' rev-parse HEAD
git -C 'E:\遥感数据展示网站' status --short
```

Expected: worktree branch is `codex/deploy-readiness`; original checkout remains `043c3be` with its existing dirty files.

- [ ] **Step 2: Apply the committed local final tree without its intermediate commits**

Run:

```powershell
git merge --squash main
```

Expected: the local application's changes are staged, but no merge commit has been created and `c8263c3` remains the branch parent.

- [ ] **Step 3: Remove generated data from the new history and ignore runtime artifacts**

Edit `.gitignore` to add exactly:

```gitignore
# Codex runtime/planning artifacts
.codex-runtime/
.planning/
test_tile*.png

# Generated deployment data (uploaded separately)
data/stats/irrigation_region_series.json
```

Edit `.dockerignore` to add:

```dockerignore
data/stats/irrigation_region_series.json
```

Run:

```powershell
git rm --cached -- data/stats/irrigation_region_series.json
git add -- .gitignore .dockerignore
git check-ignore -v data/stats/irrigation_region_series.json
```

Expected: the working-tree JSON remains on disk and is ignored; the staged tree records its deletion.

- [ ] **Step 4: Prove no staged file can violate GitHub's 100 MiB limit**

Run:

```powershell
$large = git diff --cached --name-only --diff-filter=AM | ForEach-Object {
  if (Test-Path -LiteralPath $_ -PathType Leaf) {
    $size = (Get-Item -LiteralPath $_).Length
    if ($size -ge 104857600) { "$_ $size" }
  }
}
if ($large) { $large; exit 1 }
git diff --cached --check
```

Expected: no output from `$large` and `git diff --cached --check` exits 0.

- [ ] **Step 5: Install isolated worktree dependencies and verify the reconciled baseline**

Run:

```powershell
npm ci
npm --prefix frontend ci
$env:PYTHONPATH='.'
python -m pytest backend/tests/ -q -p no:cacheprovider
npm --prefix frontend test
npm run build
```

Expected: all reconciled backend/frontend tests and the production frontend build pass before hardening changes begin.

- [ ] **Step 6: Commit the clean reconciliation**

Run:

```powershell
git add -- . ':!data/stats/irrigation_region_series.json' ':!.planning'
git commit -m "feat: reconcile local application without generated data"
```

Expected: one commit contains the local final tree; `git status --short` shows only ignored planning/data artifacts.

---

### Task 2: Centralize Runtime Configuration and Separate Writable Caches

**Files:**
- Create: `backend/runtime_config.py`
- Create: `backend/cache_io.py`
- Create: `backend/tests/test_runtime_config.py`
- Create: `backend/tests/test_cache_io.py`
- Modify: `backend/data_loader.py`
- Modify: `backend/external_rasters.py`
- Modify: `backend/irrigation_legend.py`
- Modify: `backend/irrigation_stats.py`
- Modify: `backend/routers/irrigation.py`
- Modify: `backend/routers/layers.py`
- Modify: `backend/routers/query.py`
- Modify: `backend/routers/tiles.py`
- Modify: `backend/tests/test_irrigation.py`

**Interfaces:**
- Produces: `IRRIGATION_REGION_SERIES_PATH: Path`, `CACHE_ROOT: Path`, `COUNTY_VECTOR_PATH: Path`, `TOWNSHIP_CHUNK_ROOT: Path`, `MAX_AREA_QUERY_PIXELS: int`, `ENABLE_API_DOCS: bool`, `parse_cors_origins(value: str) -> tuple[str, ...]`, and `atomic_write_json(path: Path, payload: object) -> None`.
- Consumers: readiness, query limits, application factory, preflight script, legend cache, and on-demand irrigation cache.

- [ ] **Step 1: Write failing runtime-configuration tests**

Create `backend/tests/test_runtime_config.py`:

```python
from pathlib import Path

import pytest

from backend import runtime_config


def test_parse_cors_origins_trims_and_discards_empty_values():
    assert runtime_config.parse_cors_origins(
        " http://localhost:5173, ,https://maps.example "
    ) == ("http://localhost:5173", "https://maps.example")


def test_positive_int_env_rejects_zero_and_non_numeric(monkeypatch):
    for value in ("0", "-1", "many"):
        monkeypatch.setenv("MAX_AREA_QUERY_PIXELS", value)
        with pytest.raises(RuntimeError, match="MAX_AREA_QUERY_PIXELS"):
            runtime_config.positive_int_env("MAX_AREA_QUERY_PIXELS", 4_000_000)


def test_runtime_paths_are_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_ROOT", str(tmp_path / "cache"))
    assert runtime_config.path_env("CACHE_ROOT", Path("unused")).is_absolute()
```

Run:

```powershell
$env:PYTHONPATH='.'; python -m pytest backend/tests/test_runtime_config.py -v -p no:cacheprovider
```

Expected: FAIL because `backend.runtime_config` does not exist.

- [ ] **Step 2: Implement validated runtime settings**

Create `backend/runtime_config.py` with these public definitions:

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def path_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


def positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def parse_cors_origins(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return raw == "true"


RASTER_ROOT = path_env("RASTER_ROOT", PROJECT_ROOT / "data" / "rasters")
IRRIGATION_ANNUAL_ROOT = path_env(
    "IRRIGATION_ANNUAL_ROOT", RASTER_ROOT / "irrigation_annual"
)
IRRIGATION_8DAY_ROOT = path_env(
    "IRRIGATION_8DAY_ROOT", RASTER_ROOT / "irrigation_8day"
)
IRRIGATION_ANNUAL_COG_ROOT = path_env(
    "IRRIGATION_ANNUAL_COG_ROOT", RASTER_ROOT / "irrigation_annual"
)
IRRIGATION_8DAY_COG_ROOT = path_env(
    "IRRIGATION_8DAY_COG_ROOT", RASTER_ROOT / "irrigation_8day"
)
IRRIGATION_REGION_SERIES_PATH = path_env(
    "IRRIGATION_REGION_SERIES_PATH",
    PROJECT_ROOT / "data" / "stats" / "irrigation_region_series.json",
)
CACHE_ROOT = path_env("CACHE_ROOT", PROJECT_ROOT / ".runtime-cache")
COUNTY_VECTOR_PATH = path_env(
    "COUNTY_VECTOR_PATH",
    PROJECT_ROOT / "data" / "vectors" / "irrigation" / "county" / "china_county.shp",
)
TOWNSHIP_CHUNK_ROOT = path_env(
    "TOWNSHIP_CHUNK_ROOT",
    PROJECT_ROOT / "data" / "vectors" / "irrigation" / "township_by_county",
)
MAX_AREA_QUERY_PIXELS = positive_int_env("MAX_AREA_QUERY_PIXELS", 4_000_000)
ENABLE_API_DOCS = bool_env("ENABLE_API_DOCS", False)
CORS_ORIGINS = parse_cors_origins(
    os.getenv("CORS_ORIGINS", "http://localhost:5173")
)
```

Run the focused test and expect PASS.

- [ ] **Step 3: Write failing atomic-cache tests**

Create `backend/tests/test_cache_io.py`:

```python
import json

from backend.cache_io import atomic_write_json


def test_atomic_write_json_replaces_complete_file(tmp_path):
    target = tmp_path / "cache" / "legend.json"
    target.parent.mkdir()
    target.write_text('{"old": true}', encoding="utf-8")

    atomic_write_json(target, {"new": [1, 2, 3]})

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": [1, 2, 3]}
    assert list(target.parent.glob("*.tmp")) == []


def test_legend_cache_write_does_not_modify_read_only_seed(monkeypatch, tmp_path):
    from backend import irrigation_legend
    seed = tmp_path / "source" / "irrigation_legends.json"
    seed.parent.mkdir()
    seed.write_text('{"seed": true}', encoding="utf-8")
    runtime = tmp_path / "cache" / "irrigation_legends.json"
    monkeypatch.setattr(irrigation_legend, "_LEGEND_SEED_PATH", seed)
    monkeypatch.setattr(irrigation_legend, "_LEGEND_CACHE_PATH", runtime)
    irrigation_legend._save_legend_disk_cache({"runtime": True})
    assert json.loads(seed.read_text(encoding="utf-8")) == {"seed": True}
    assert json.loads(runtime.read_text(encoding="utf-8")) == {"runtime": True}
```

Run and expect FAIL because `backend.cache_io` does not exist.

- [ ] **Step 4: Implement atomic JSON publication and redirect caches**

Create `backend/cache_io.py`:

```python
import json
import os
import tempfile
from pathlib import Path


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
```

Then update:

- `data_loader.get_irrigation_region_series()` to open `IRRIGATION_REGION_SERIES_PATH` directly;
- `data_loader` to import all irrigation raster roots from `runtime_config` instead of keeping Windows drive defaults;
- `external_rasters`, `routers/layers.py`, `routers/query.py`, and `routers/tiles.py` to resolve project raster subdirectories beneath `RASTER_ROOT`;
- `irrigation_legend` to read `$CACHE_ROOT/irrigation_legends.json`, falling back to tracked `data/stats/irrigation_legends.json`, and publish through `atomic_write_json`;
- `irrigation_stats` to read `$CACHE_ROOT/irrigation_computed_series.json`, falling back to its tracked seed, and publish atomically;
- `routers/irrigation.py` to import `COUNTY_VECTOR_PATH` and `TOWNSHIP_CHUNK_ROOT` from `runtime_config` instead of defining Windows/project paths locally.

Update existing data-loader tests to monkeypatch `IRRIGATION_REGION_SERIES_PATH` rather than `PROJECT_ROOT`.

- [ ] **Step 5: Verify focused and regression tests**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_runtime_config.py backend/tests/test_cache_io.py backend/tests/test_irrigation.py -v -p no:cacheprovider
```

Expected: all focused tests pass and no cache test writes into `data/stats`.

- [ ] **Step 6: Commit runtime boundaries**

```powershell
git add backend/runtime_config.py backend/cache_io.py backend/data_loader.py backend/external_rasters.py backend/irrigation_legend.py backend/irrigation_stats.py backend/routers/irrigation.py backend/routers/layers.py backend/routers/query.py backend/routers/tiles.py backend/tests/test_runtime_config.py backend/tests/test_cache_io.py backend/tests/test_irrigation.py
git commit -m "refactor: separate runtime data and cache paths"
```

---

### Task 3: Add Readiness and Deployment Data Preflight

**Files:**
- Create: `backend/readiness.py`
- Create: `scripts/check_deployment_data.py`
- Create: `backend/tests/test_readiness.py`
- Create: `backend/tests/test_deployment_preflight.py`
- Modify: `backend/routers/health.py`
- Modify: `backend/tests/test_health.py`

**Interfaces:**
- Produces: `collect_readiness_failures() -> list[str]`, `probe_json_object(path: Path) -> bool`, `/api/ready`, and preflight process exit codes 0/1.
- Consumes: runtime paths from `backend.runtime_config`, irrigation raster roots from `backend.data_loader`, and external roots from `backend.external_rasters.EXTERNAL_RASTERS`.

- [ ] **Step 1: Write failing readiness tests**

Create `backend/tests/test_readiness.py` with temporary runtime paths and these core assertions:

```python
import json

from backend import readiness


def install_complete_runtime(monkeypatch, tmp_path):
    series = tmp_path / "stats" / "irrigation_region_series.json"
    series.parent.mkdir()
    series.write_text('{"county": {}}', encoding="utf-8")
    county = tmp_path / "vectors" / "county" / "china_county.shp"
    county.parent.mkdir(parents=True)
    for suffix in (".shp", ".shx", ".dbf"):
        county.with_suffix(suffix).write_bytes(b"x")
    township = tmp_path / "vectors" / "township_by_county"
    township.mkdir()
    (township / "manifest.json").write_text("{}", encoding="utf-8")
    raster_roots = []
    for name in ("ssm", "et", "sm_10cm", "sm_30cm", "sm_60cm", "sm_100cm", "irrigation_annual", "irrigation_8day"):
        root = tmp_path / "rasters" / name
        root.mkdir(parents=True)
        (root / "sample.tif").write_bytes(b"x")
        raster_roots.append((name, root))
    monkeypatch.setattr(readiness, "IRRIGATION_REGION_SERIES_PATH", series)
    monkeypatch.setattr(readiness, "COUNTY_VECTOR_PATH", county)
    monkeypatch.setattr(readiness, "TOWNSHIP_CHUNK_ROOT", township)
    monkeypatch.setattr(readiness, "required_raster_roots", lambda: raster_roots)


def test_complete_runtime_is_ready(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    assert readiness.collect_readiness_failures() == []


def test_readiness_uses_identifiers_not_host_paths(monkeypatch, tmp_path):
    install_complete_runtime(monkeypatch, tmp_path)
    readiness.IRRIGATION_REGION_SERIES_PATH.unlink()
    failures = readiness.collect_readiness_failures()
    assert failures == ["irrigation_region_series"]
    assert str(tmp_path) not in json.dumps(failures)
```

Run and expect FAIL because `backend.readiness` does not exist.

- [ ] **Step 2: Implement reusable readiness probes**

Create `backend/readiness.py` with:

```python
import json
from functools import lru_cache
from pathlib import Path

from backend.runtime_config import (
    COUNTY_VECTOR_PATH,
    IRRIGATION_8DAY_ROOT,
    IRRIGATION_ANNUAL_ROOT,
    IRRIGATION_REGION_SERIES_PATH,
    RASTER_ROOT,
    TOWNSHIP_CHUNK_ROOT,
)


@lru_cache(maxsize=8)
def _cached_json_probe(path: str, mtime_ns: int, size: int) -> bool:
    del mtime_ns, size
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return isinstance(json.load(handle), dict)
    except (OSError, json.JSONDecodeError):
        return False


def probe_json_object(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return stat.st_size > 0 and _cached_json_probe(str(path), stat.st_mtime_ns, stat.st_size)


def required_raster_roots() -> list[tuple[str, Path]]:
    roots = [
        (identifier, RASTER_ROOT / identifier)
        for identifier in ("ssm", "et", "sm_10cm", "sm_30cm", "sm_60cm", "sm_100cm")
    ]
    roots.extend((
        ("irrigation_annual", IRRIGATION_ANNUAL_ROOT),
        ("irrigation_8day", IRRIGATION_8DAY_ROOT),
    ))
    return roots


def _contains_tiff(root: Path) -> bool:
    return root.is_dir() and any(
        path.is_file() and path.suffix.lower() in {".tif", ".tiff"}
        for path in root.iterdir()
    )


def collect_readiness_failures() -> list[str]:
    failures = []
    if not probe_json_object(IRRIGATION_REGION_SERIES_PATH):
        failures.append("irrigation_region_series")
    if not all(COUNTY_VECTOR_PATH.with_suffix(suffix).is_file() for suffix in (".shp", ".shx", ".dbf")):
        failures.append("county_vector")
    if not (TOWNSHIP_CHUNK_ROOT / "manifest.json").is_file():
        failures.append("township_chunks")
    failures.extend(identifier for identifier, root in required_raster_roots() if not _contains_tiff(root))
    return failures
```

- [ ] **Step 3: Add the readiness API and witness GREEN**

Update `backend/routers/health.py`:

```python
from fastapi import APIRouter, Response, status
from backend.readiness import collect_readiness_failures

router = APIRouter(tags=["health"])

@router.get("/health")
def health_check():
    return {"status": "ok", "message": "Service is healthy"}

@router.get("/ready")
def readiness_check(response: Response):
    failures = collect_readiness_failures()
    if failures:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "dependencies": failures}
    return {"status": "ready", "dependencies": []}
```

Add API tests that monkeypatch `backend.routers.health.collect_readiness_failures` to `[]` and `["county_vector"]`, then assert 200/503 and the exact JSON bodies. Run `test_readiness.py` and `test_health.py`; expect PASS.

- [ ] **Step 4: Write failing preflight tests and implement the CLI**

Create `backend/tests/test_deployment_preflight.py`:

```python
from scripts import check_deployment_data


def test_preflight_returns_zero_when_ready(monkeypatch, capsys):
    monkeypatch.setattr(check_deployment_data, "collect_readiness_failures", lambda: [])
    assert check_deployment_data.main() == 0
    assert "deployment data ready" in capsys.readouterr().out.lower()


def test_preflight_returns_one_with_stable_identifiers(monkeypatch, capsys):
    monkeypatch.setattr(check_deployment_data, "collect_readiness_failures", lambda: ["county_vector"])
    assert check_deployment_data.main() == 1
    assert capsys.readouterr().err.strip() == "missing or invalid: county_vector"
```

Create `scripts/check_deployment_data.py`:

```python
from __future__ import annotations
import sys
from backend.readiness import collect_readiness_failures


def main() -> int:
    failures = collect_readiness_failures()
    if failures:
        print(f"missing or invalid: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("Deployment data ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run the two focused files and expect PASS.

- [ ] **Step 5: Commit readiness and preflight**

```powershell
git add backend/readiness.py backend/routers/health.py backend/tests/test_readiness.py backend/tests/test_health.py backend/tests/test_deployment_preflight.py scripts/check_deployment_data.py
git commit -m "feat: add deployment data readiness checks"
```

---

### Task 4: Reject Oversized Raster Area Queries Before Reads

**Files:**
- Modify: `backend/routers/query.py`
- Modify: `backend/tests/test_query.py`

**Interfaces:**
- Consumes: `MAX_AREA_QUERY_PIXELS` from `backend.runtime_config`.
- Produces: `_enforce_area_pixel_limit(row_min: int, row_max: int, col_min: int, col_max: int) -> None`; HTTP 413 detail `{code, maxPixels}`.

- [ ] **Step 1: Write failing guard and no-read tests**

Add to `backend/tests/test_query.py`:

```python
def test_area_pixel_limit_returns_stable_413(monkeypatch):
    monkeypatch.setattr(query, "MAX_AREA_QUERY_PIXELS", 4)
    with pytest.raises(HTTPException) as exc_info:
        query._enforce_area_pixel_limit(0, 3, 0, 2)
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == {
        "code": "query_window_too_large",
        "maxPixels": 4,
    }


def test_ssm_oversized_area_fails_before_raster_read(monkeypatch, tmp_path):
    raster = patch_ssm_raster(monkeypatch, tmp_path, np.ones((3, 2)))
    monkeypatch.setattr(query, "MAX_AREA_QUERY_PIXELS", 4)
    with pytest.raises(HTTPException) as exc_info:
        query._query_area_SSM({"id": "ssm"}, "2025_01", 0, 0, 1, 1)
    assert exc_info.value.status_code == 413
    assert raster.read_windows == []
```

Run the two tests and expect FAIL because the helper does not exist and reads currently occur.

- [ ] **Step 2: Implement the shared guard and call it from every raster area path**

Add to `backend/routers/query.py`:

```python
from backend.runtime_config import MAX_AREA_QUERY_PIXELS


def _enforce_area_pixel_limit(row_min: int, row_max: int, col_min: int, col_max: int) -> None:
    pixels = max(0, row_max - row_min) * max(0, col_max - col_min)
    if pixels > MAX_AREA_QUERY_PIXELS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "query_window_too_large",
                "maxPixels": MAX_AREA_QUERY_PIXELS,
            },
        )
```

Call it immediately after empty-window validation in `_query_area_SSM`, `_query_area_external`, and `_query_area_irrigation`, before the first `read()` or `read_masks()` call.

- [ ] **Step 3: Add call-site regression coverage and witness GREEN**

Add equivalent no-read tests for external rasters and irrigation rasters using their existing fake Rasterio sources. Assert exact 413 detail and empty `read_windows`. Run:

```powershell
$env:PYTHONPATH='.'; python -m pytest backend/tests/test_query.py -v -p no:cacheprovider
```

Expected: all query tests pass.

- [ ] **Step 4: Commit the bounded-query behavior**

```powershell
git add backend/routers/query.py backend/tests/test_query.py
git commit -m "fix: bound raster area query windows"
```

---

### Task 5: Harden FastAPI Defaults and Tile Cache Semantics

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/routers/tiles.py`
- Create: `backend/tests/test_app_config.py`
- Modify: `backend/tests/test_tiles.py`

**Interfaces:**
- Produces: `create_app(enable_api_docs: bool | None = None, cors_origins: tuple[str, ...] | None = None) -> FastAPI` and `TILE_CACHE_HEADERS`.
- Consumes: `ENABLE_API_DOCS` and `CORS_ORIGINS` from runtime configuration.

- [ ] **Step 1: Write failing app-factory tests**

Create `backend/tests/test_app_config.py`:

```python
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
    assert response.headers["access-control-allow-origin"] == "https://maps.example"
```

Run and expect FAIL because `create_app` does not exist.

- [ ] **Step 2: Refactor app creation without changing routes**

Implement `create_app()` in `backend/main.py`, passing `docs_url`, `redoc_url`, and `openapi_url` as `None` when docs are disabled. Add CORS middleware only when the chosen origins tuple is non-empty, include the same routers/prefixes as today, and set module-level `app = create_app()`.

Run `test_app_config.py`, `test_health.py`, and the existing router tests; expect PASS.

- [ ] **Step 3: Write failing tile-cache tests**

Extend existing route tests to assert:

```python
assert response.headers["cache-control"] == "public, max-age=604800, immutable"
```

Cover the SSM, external raster, irrigation raster, and transparent-outside-bounds success paths. Run the four tests and expect FAIL because responses lack this header.

- [ ] **Step 4: Add one shared cache-header mapping**

In `backend/routers/tiles.py` define:

```python
TILE_CACHE_HEADERS = {"Cache-Control": "public, max-age=604800, immutable"}
```

Pass `headers=TILE_CACHE_HEADERS` to every successful dynamic PNG `Response`, including transparent out-of-bounds responses. Do not add it to errors.

Run `test_app_config.py` and `test_tiles.py`; expect PASS.

- [ ] **Step 5: Commit API and tile hardening**

```powershell
git add backend/main.py backend/routers/tiles.py backend/tests/test_app_config.py backend/tests/test_tiles.py
git commit -m "feat: harden API and tile cache defaults"
```

---

### Task 6: Replace the Deployment Stack with Caddy and Internal Unprivileged Services

**Files:**
- Create: `Caddyfile`
- Modify: `Dockerfile.backend`
- Modify: `Dockerfile.frontend`
- Modify: `docker-compose.yml`
- Modify: `nginx.conf`
- Modify: `.env.example`
- Create: `backend/tests/test_deployment_config.py`
- Create: `backend/requirements-dev.txt`

**Interfaces:**
- Consumes: `/api/ready`, runtime-data paths, cache root, query limit, tile cache headers.
- Produces: `edge`, `frontend`, and `backend` Compose services; `SITE_ADDRESS=:80`; internal ports 8080/8000; Caddy automatic HTTPS after a domain is supplied.

- [ ] **Step 1: Write failing deployment-contract tests**

Create `backend/requirements-dev.txt` before running the YAML contract tests:

```text
-r requirements.txt
pytest==8.3.4
httpx==0.28.1
PyYAML==6.0.2
rio-cogeo==7.0.2
```

Install it with `python -m pip install -r backend/requirements-dev.txt` in the isolated environment. This file is refined, not recreated, in Task 7.

Create `backend/tests/test_deployment_config.py`:

```python
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


def compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_only_caddy_publishes_host_ports():
    services = compose()["services"]
    assert services["edge"]["ports"] == ["80:80", "443:443"]
    assert "ports" not in services["frontend"]
    assert "ports" not in services["backend"]


def test_backend_runtime_mounts_and_defaults_are_safe():
    backend = compose()["services"]["backend"]
    volumes = backend["volumes"]
    assert any(item["target"] == "/app/runtime-data/stats" and item["read_only"] for item in volumes if isinstance(item, dict))
    assert any(item["target"] == "/app/cache" for item in volumes if isinstance(item, dict))
    bind_mounts = [item for item in volumes if isinstance(item, dict) and item.get("type") == "bind"]
    assert all(item["bind"]["create_host_path"] is False for item in bind_mounts)
    environment = backend["environment"]
    assert environment["UVICORN_WORKERS"] == "${UVICORN_WORKERS:-1}"
    assert environment["GDAL_CACHEMAX"] == "${GDAL_CACHEMAX:-256}"
    assert environment["MAX_AREA_QUERY_PIXELS"] == "${MAX_AREA_QUERY_PIXELS:-4000000}"
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
    assert (ROOT / "Caddyfile").read_text(encoding="utf-8").splitlines()[0] == "{$SITE_ADDRESS} {"
```

Run and expect FAIL against the current two-service, port-80 Nginx stack.

- [ ] **Step 2: Implement the Caddy edge and Compose topology**

Create `Caddyfile`:

```caddyfile
{$SITE_ADDRESS} {
    encode zstd gzip
    reverse_proxy frontend:8080
}
```

Replace `docker-compose.yml` so:

- `edge` uses `caddy:2.10-alpine`, publishes `80:80` and `443:443`, sets `SITE_ADDRESS=${SITE_ADDRESS:-:80}`, mounts `Caddyfile`, `caddy_data`, and `caddy_config`, and waits for healthy frontend;
- `frontend` has no host ports, exposes 8080, and waits for healthy backend;
- `backend` has no host ports, exposes 8000, uses long-form read-only mounts for `./data/rasters`, `./data/vectors`, and `./data/stats` at `/app/runtime-data/stats`, plus named volume `backend_cache:/app/cache`;
- every bind uses long-form `bind.create_host_path: false`; backend environment sets `RASTER_ROOT=/app/data/rasters`, `IRRIGATION_REGION_SERIES_PATH=/app/runtime-data/stats/irrigation_region_series.json`, `COUNTY_VECTOR_PATH=/app/data/vectors/irrigation/county/china_county.shp`, `TOWNSHIP_CHUNK_ROOT=/app/data/vectors/irrigation/township_by_county`, `CACHE_ROOT=/app/cache`, and the approved defaults;
- named volumes are `backend_cache`, `caddy_data`, and `caddy_config`.

- [ ] **Step 3: Make both application images unprivileged**

In `Dockerfile.backend`, use `python:3.12-slim-bookworm`, install only Python wheels required by `backend/requirements.txt` (remove the current compiler/GDAL development package layer), create UID/GID 10001 `app`, copy application files with `--chown=app:app`, switch to `USER app`, use `/api/ready` with `--start-period=120s`, and run:

```dockerfile
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1} --timeout-keep-alive 65"]
```

In `Dockerfile.frontend`, keep `node:22-alpine` for the builder and use `nginxinc/nginx-unprivileged:1.28-alpine` for runtime. Copy `nginx.conf` to `/etc/nginx/conf.d/default.conf`, expose 8080, and health-check `http://localhost:8080/`.

- [ ] **Step 4: Implement rate limits and tile caching in Nginx**

At `nginx.conf` HTTP include scope, define:

```nginx
limit_req_zone $binary_remote_addr zone=api_rate:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=area_rate:10m rate=1r/s;
limit_req_zone $binary_remote_addr zone=tile_rate:10m rate=20r/s;
limit_conn_zone $binary_remote_addr zone=client_conn:10m;
proxy_cache_path /tmp/nginx-cache levels=1:2 keys_zone=tile_cache:20m max_size=1g inactive=7d use_temp_path=off;
```

Trust only the Docker bridge range for the Caddy-provided client address using `set_real_ip_from 172.16.0.0/12`, `real_ip_header X-Forwarded-For`, and `real_ip_recursive on`. Listen on 8080, set `limit_req_status 429`, limit general API to burst 20, exact `/api/query/area` to burst 3 and four concurrent upstream connections, and `/cog/` plus dynamic `/data/*-tiles/` to burst 50 with `proxy_cache tile_cache`, `proxy_cache_valid 200 7d`, and errors uncached through `proxy_no_cache $upstream_http_set_cookie` plus cache validity defined only for 200 responses.

- [ ] **Step 5: Update environment examples and witness GREEN**

Update `.env.example` with exact defaults and explanations for `SITE_ADDRESS`, `UVICORN_WORKERS`, `GDAL_CACHEMAX`, `MAX_AREA_QUERY_PIXELS`, `ENABLE_API_DOCS`, all runtime data paths, and cache root. Run:

```powershell
$env:PYTHONPATH='.'; python -m pytest backend/tests/test_deployment_config.py -v -p no:cacheprovider
```

Expected: all deployment contract tests pass. Do not invoke Docker.

- [ ] **Step 6: Commit the deployment topology**

```powershell
git add Caddyfile Dockerfile.backend Dockerfile.frontend docker-compose.yml nginx.conf .env.example backend/requirements-dev.txt backend/tests/test_deployment_config.py
git commit -m "feat: harden single-server deployment topology"
```

---

### Task 7: Split Dependencies, Remove Dead Features, and Document Operations

**Files:**
- Modify: `backend/requirements.txt`
- Inspect: `backend/requirements-dev.txt`
- Delete: `backend/auth.py`
- Delete: `backend/routers/auth.py`
- Delete: `backend/routers/export.py`
- Modify: `package.json`
- Modify: `README.md`
- Create: `docs/deployment.md`
- Create: `.github/workflows/ci.yml`
- Modify: `backend/tests/test_deployment_config.py`

**Interfaces:**
- Produces: minimal production dependencies, reproducible developer/test installation, accurate deployment runbook, and non-Docker CI.
- Consumes: all prior runtime variables, preflight command, readiness route, Compose service names, and validation commands.

- [ ] **Step 1: Write failing repository-hygiene assertions**

Extend `backend/tests/test_deployment_config.py`:

```python
def test_runtime_requirements_exclude_test_and_removed_auth_packages():
    runtime = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    for removed in ("pytest", "httpx", "PyJWT", "bcrypt", "python-multipart"):
        assert removed not in runtime
    for direct in ("numpy==", "rasterio==", "pyproj==", "rio-tiler=="):
        assert direct in runtime


def test_ci_does_not_build_docker_images():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest backend/tests/" in workflow
    assert "npm run build" in workflow
    assert "docker build" not in workflow
    assert "docker compose build" not in workflow
```

Run and expect FAIL because dependency split and CI do not exist.

- [ ] **Step 2: Split and pin dependency files**

Set `backend/requirements.txt` to:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
python-dotenv==1.0.1
pydantic==2.10.3
numpy==2.2.6
rasterio==1.4.3
pyproj==3.7.1
titiler.core==0.19.3
rio-tiler==7.8.1
```

Keep `backend/requirements-dev.txt` from Task 6 with this exact content:

```text
-r requirements.txt
pytest==8.3.4
httpx==0.28.1
PyYAML==6.0.2
rio-cogeo==7.0.2
```

Update root `package.json` so `install:all` installs `backend/requirements-dev.txt`; keep production Docker using only `backend/requirements.txt`.

- [ ] **Step 3: Remove unreachable auth/export code**

Delete `backend/auth.py`, `backend/routers/auth.py`, and `backend/routers/export.py`. Run:

```powershell
rg -n 'backend\.auth|routers import auth|routers import export|viewer123|researcher123' backend frontend README.md
```

Expected: no application references remain; matches in the old README disappear in Step 4.

- [ ] **Step 4: Rewrite user and operator documentation**

Rewrite `README.md` to cover the actual SSM, ET, four soil-depth, irrigation raster, and administrative drilldown features; local development; tests; the separate-data policy; and a pointer to `docs/deployment.md`. Remove sample credentials, JWT, CSV export, NDVI, precipitation, LST, and ECharts claims.

Create `docs/deployment.md` with executable sections for:

```powershell
Copy-Item .env.example .env
python scripts/check_deployment_data.py
```

and Linux server commands for directory creation, `rsync`/SFTP data upload, HTTP startup prerequisites, `/api/ready` and representative irrigation-average smoke checks, worker/GDAL sizing, named-volume/data backup, log inspection, rollback by Git commit, and changing `SITE_ADDRESS` from `:80` to a DNS name after DNS propagation.

- [ ] **Step 5: Add non-Docker GitHub Actions CI**

Create `.github/workflows/ci.yml` with `push` and `pull_request` triggers, one Python 3.12 backend job that installs `backend/requirements-dev.txt` and runs `pytest backend/tests/ -v`, and one Node 22 frontend job that runs `npm ci`, `npm --prefix frontend ci`, frontend test, lint, and `npm run build`. Do not add Docker steps.

- [ ] **Step 6: Witness GREEN and commit**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_deployment_config.py -v -p no:cacheprovider
rg -n 'viewer123|researcher123|JWT 登录|CSV 导出' README.md backend frontend
```

Expected: deployment tests pass and the removed-feature scan has no matches.

Commit:

```powershell
git add backend/requirements.txt package.json README.md docs/deployment.md .github/workflows/ci.yml backend/tests/test_deployment_config.py
git add -u backend/auth.py backend/routers/auth.py backend/routers/export.py
git commit -m "chore: document and automate deployment readiness"
```

---

### Task 8: Complete Non-Docker Verification and Publish a Draft PR

**Files:**
- Modify only if verification exposes a scoped defect.
- Inspect: all branch changes against `origin/main`.

**Interfaces:**
- Produces: verified branch `codex/deploy-readiness` and a draft PR to `main`.
- Consumes: every acceptance criterion from the approved specification.

- [ ] **Step 1: Re-read the specification and plan**

Run:

```powershell
Get-Content -Raw docs/superpowers/specs/2026-07-18-deployment-readiness-design.md
Get-Content -Raw docs/superpowers/plans/2026-07-18-deployment-readiness.md
```

Expected: every specification section maps to Tasks 1–7; Docker validation remains deferred.

- [ ] **Step 2: Run complete backend and frontend verification**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/ -v -p no:cacheprovider
npm --prefix frontend test
npm --prefix frontend run lint
npm run build
npm --prefix frontend audit --omit=dev --audit-level=high --registry=https://registry.npmjs.org
```

Expected: all tests and build pass; lint has zero errors; production dependency audit exits 0. Record warnings exactly rather than hiding them.

- [ ] **Step 3: Run local readiness and representative API smoke tests**

Start one hidden Uvicorn process on port 8123, then verify:

```text
GET /api/health -> 200 status=ok
GET /api/ready -> 200 status=ready
GET /api/layers -> 200
GET /api/irrigation/regions/averages?level=county -> 200, 2893 averages, 6 legend stops
```

Stop only the process started by this step. If the isolated worktree lacks ignored runtime data, point its environment variables to the original workspace data directories; do not copy or commit the datasets.

- [ ] **Step 4: Prove branch size and original-worktree safety**

Run:

```powershell
$objects = git rev-list --objects origin/main..HEAD | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)'
$large = $objects | Where-Object { ($_ -split ' ')[0] -eq 'blob' -and [int64](($_ -split ' ')[1]) -ge 104857600 }
if ($large) { $large; exit 1 }
git check-ignore -v data/stats/irrigation_region_series.json
git -C 'E:\遥感数据展示网站' rev-parse HEAD
git -C 'E:\遥感数据展示网站' status --short
```

Expected: no branch blob is 100 MiB or larger; the generated file is ignored; original `main` remains at `043c3be` with its pre-existing dirty state.

- [ ] **Step 5: Review final scope and commit any verification-only correction**

Run:

```powershell
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git status --short --branch
```

Expected: no unstaged production changes, no `.planning` files tracked, and no generated data in the diff.

- [ ] **Step 6: Push and open a draft pull request**

Run:

```powershell
gh auth status
git push -u origin codex/deploy-readiness
```

Open a draft PR titled `feat: prepare single-server production deployment` against `main`. Its body must summarize Git-history reconciliation, separate runtime data, Caddy/IP-to-domain flow, readiness, query/rate limits, cache and worker defaults, dependency cleanup, verification results, and the explicit fact that Docker build/runtime validation is deferred.

Expected: branch is available on GitHub and the draft PR URL is recorded; remote `main` is unchanged.

---

## Deferred Docker Validation

After the user approves the source/configuration result and Docker is available, create a separate plan/checkpoint for `docker compose config`, clean image builds, container user inspection, health/readiness startup, mounted-data smoke tests, Caddy HTTP access, restart persistence, resource observation, and later TLS-domain validation. None of those commands belong to this implementation plan.
