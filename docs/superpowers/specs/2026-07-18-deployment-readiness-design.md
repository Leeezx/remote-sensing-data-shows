# Deployment Readiness and Git Reconciliation Design

## Purpose

Bring the committed local application changes onto a clean GitHub-ready branch without publishing generated data, then make the repository safe and operable for a single-server public deployment. The first deployment will use a public IP over HTTP because no server or domain has been purchased. A later domain must enable automatic HTTPS without changing application code.

Docker image construction and container runtime validation are explicitly deferred until the source and configuration changes in this design are complete.

## Git and Data Reconciliation

The working branch is `codex/deploy-readiness`, created from `origin/main` at `5d1aeca`. The original local `main` at `043c3be`, including all uncommitted and untracked files in its worktree, remains unchanged.

Implementation will apply the final committed tree difference from local `main` to the clean branch without preserving the three unpublished intermediate commits. Before creating replacement history, it will remove `data/stats/irrigation_region_series.json` from Git tracking and add an ignore rule for that exact generated file. This prevents the 228,658,900-byte ordinary Git blob from appearing anywhere in the new branch history.

Large runtime data remains on the operator's machine and will be uploaded separately to the server. The deployment expects these host paths:

- `data/rasters/` for all COG raster datasets;
- `data/vectors/` for county vectors and township chunks;
- `data/stats/irrigation_region_series.json` for the generated administrative time-series dataset.

Small metadata and catalog files remain tracked when they are part of the application contract. The large time-series path becomes configurable so local development can continue to use the existing file while containers read it from a read-only runtime-data mount.

The clean branch will be pushed to GitHub and opened as a draft pull request against `main`. It will not force-push or directly rewrite remote `main`.

## Service Architecture

The Compose stack contains three public-runtime services:

1. `edge`: Caddy is the only service with host ports. It listens on 80 and 443, proxies the site to the frontend service, and persists Caddy state in named volumes. `SITE_ADDRESS=:80` is the default for IP-based HTTP. Replacing it with a DNS name after that name resolves to the server activates Caddy's automatic HTTPS.
2. `frontend`: an unprivileged Nginx image serves the Vite build on port 8080 and proxies `/api`, `/data`, and `/cog` to the backend. It is reachable only on the Compose network.
3. `backend`: FastAPI runs as a non-root user and is reachable only on the Compose network. `UVICORN_WORKERS` defaults to `1`; operators may raise it only after memory testing.

The existing frontend's relative API URLs remain unchanged. Caddy does not need route-specific application knowledge because the frontend proxy remains the single internal origin.

Base images must use explicit versioned tags rather than `latest`. Production Python dependencies and development/test dependencies will be separated. Direct runtime imports of NumPy and Rasterio must be declared explicitly, and `rio-cogeo` must use a bounded version rather than an open-ended lower bound.

## Runtime Data and Cache Boundaries

Raster, vector, and large statistics mounts are read-only. Runtime cache writes go to `/app/cache`, backed by a named volume. Cache paths are configured independently from source-data paths.

Cache file publication uses same-directory temporary files plus atomic replacement. The default single-worker configuration prevents normal multi-process lost updates. Increasing the worker count is an operator-controlled optimization and must not be presented as safe without load and cache-contention testing.

`GDAL_CACHEMAX` defaults to `256` MB. This value is per backend process, so the documentation will explain that both the GDAL cache and the roughly 1 GiB administrative-series working set scale with worker count.

## Health and Readiness

`GET /api/health` remains a lightweight liveness endpoint that proves the Python service loop is responsive.

A new `GET /api/ready` endpoint returns 200 only when all required runtime inputs are usable. It checks:

- the configured administrative-series file exists, is a regular non-empty file, and its JSON root can be decoded as an object through a cached probe;
- every configured raster root exists and contains at least one matching TIFF;
- the county vector source exists;
- the township chunk directory and its manifest exist.

Failures return HTTP 503 with a stable response containing `status: "not_ready"` and a list of missing or invalid dependency identifiers. The response must not expose host filesystem paths. Compose backend health checks use `/api/ready`; liveness remains available for diagnostics.

The backend health check uses a 120-second start period so the first validation of the large statistics file is not treated as a crash on slower disks. A deployment preflight command validates the required host directories and large statistics file before Compose starts, preventing Docker from silently replacing a missing bind source with an empty directory.

## Public-Request Protection

Area queries must reject raster windows above `MAX_AREA_QUERY_PIXELS`, which defaults to `4000000`. The limit is evaluated after transforming and clipping the requested bounds to the raster but before allocating or reading the raster window. Oversized requests return HTTP 413 with the stable code `query_window_too_large` and include the configured pixel limit, not internal raster paths.

The frontend proxy applies separate per-client limits:

- general API requests: 10 requests per second with a burst of 20;
- area-query requests: 1 request per second with a burst of 3;
- dynamic tile requests: 20 requests per second with a burst of 50;
- concurrent expensive upstream requests: 4 per client.

Dynamic raster tiles receive public cache headers and use an Nginx proxy cache keyed by the complete request URI. Successful immutable time/tile responses may be cached for seven days; errors are not cached. Static hashed frontend assets retain their one-year immutable cache policy.

FastAPI documentation endpoints are disabled by default in production through `ENABLE_API_DOCS=false` and may be enabled explicitly for an internal environment. CORS origins are trimmed, empty entries are discarded, and same-origin browser access through Caddy does not require a wildcard origin.

## Repository and Documentation Hygiene

The repository ignores `.codex-runtime/`, `.planning/`, `test_tile*.png`, and the generated administrative-series file. It does not automatically add unrelated planning documents or runtime logs from the original dirty worktree.

The obsolete authentication module, sample credentials, and authentication-only dependencies are removed because the running application no longer mounts an authentication router. The README is rewritten to describe the actual ET, soil-water, and irrigation application rather than removed NDVI/auth/export features.

Deployment documentation covers:

- required server directories and separate data upload;
- `.env` creation with `SITE_ADDRESS=:80` before a domain exists;
- readiness and representative API checks;
- worker/GDAL memory sizing;
- named-volume and data-directory backup;
- log inspection, rollback to a previous Git commit, and later domain cutover.

`scripts/check_deployment_data.py` implements the documented preflight without opening raster contents: it verifies the required directories, representative TIFF presence, county source, township manifest, and non-empty administrative-series file. It exits nonzero with stable dependency identifiers when deployment data is incomplete.

A GitHub Actions workflow runs backend tests, frontend tests, lint, and the production frontend build for branches and pull requests. It does not build Docker images in this phase. Docker build and runtime verification remain a separate user-approved follow-up.

## Error Handling

Missing deployment data produces readiness 503 responses and keeps dependent services from being marked healthy. It does not silently create empty host data directories or claim readiness.

Oversized spatial queries fail before raster allocation. Rate-limited requests use standard 429 responses. Cache-write failures do not corrupt the last valid cache file; the request may still return the computed in-memory result when safe.

Configuration values are validated at startup where possible. Invalid numeric limits, empty required runtime paths, or unsupported worker values cause an explicit startup failure rather than falling back silently.

## Test and Acceptance Strategy

Behavior changes follow red-green-refactor:

- readiness tests cover complete data, each missing dependency class, malformed statistics JSON, stable 503 output, and path redaction;
- area-query tests prove an oversized window fails before Rasterio reads and a boundary-sized window proceeds;
- cache tests prove source data remains read-only and cache publication is atomic;
- application configuration tests cover trimmed CORS values and production API-doc disabling;
- deployment contract tests parse Compose/YAML and assert public-port, read-only-mount, worker, cache, health-check, and non-root invariants;
- deployment preflight tests cover complete data, missing bind sources, and stable non-sensitive error output;
- proxy configuration checks assert the approved limits, caching, and internal-only frontend/backend topology.

Final non-Docker verification consists of the complete backend test suite, complete frontend test suite, frontend lint, frontend production build, dependency audit where available, Git large-blob scan, and local API smoke tests. No completion claim may include Docker image success until Docker is installed and the separately approved container validation is run.

## Acceptance Criteria

- The new branch contains the committed local application's final behavior and deployment changes but no Git blob at or above 100 MiB.
- The large administrative-series file remains present locally for development and is ignored by Git.
- The original local `main` worktree and its dirty files are unchanged.
- Only Caddy publishes host ports; frontend and backend are internal and unprivileged.
- IP-based HTTP works through `SITE_ADDRESS=:80`, and a later domain requires only changing `SITE_ADDRESS` plus DNS.
- Missing runtime data makes readiness fail with a non-sensitive 503 response.
- Oversized area queries are rejected before raster reads.
- Production defaults use one backend worker and a 256 MB GDAL cache.
- All non-Docker checks pass, and the branch is published as a draft pull request without directly changing remote `main`.
