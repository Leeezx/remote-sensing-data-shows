# Reclamation Potential Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/reclamation` placeholder with a China-overview-to-demo-region drill-down map that renders current and future reclamation scenarios as an interactive, browser-side Canvas layer.

**Architecture:** An offline Python builder validates the Excel/Shapefile sources, spatially partitions points by the four WGS84 demo polygons, dissolves a checked-in China outline, and writes deterministic raw/gzip artifacts. FastAPI serves only those immutable artifacts with cache headers; React loads the overview first, fetches one selected region once, parses compact tuples at the API boundary, and renders at most 8,702 points through one Leaflet Canvas overlay component.

**Tech Stack:** Python 3, FastAPI, pytest, openpyxl, Shapely, React 19, TypeScript 6, React-Leaflet 5, Leaflet 1.9, Axios, Vitest, Testing Library, HTML Canvas 2D.

## Global Constraints

- Production server target is 2 CPU cores and 4 GB RAM; runtime must not parse Excel, dissolve geometry, generate tiles, or query one point at a time.
- Runtime must not depend on `C:\Users\Administrator\Desktop\复耕潜力数据` or `F:\矢量底图\中国_县\中国_县.shp`.
- All published geometries and coordinates use WGS84 / EPSG:4326.
- Every region `bounds` value uses Leaflet order `[[south, west], [north, east]]`.
- `/reclamation` initially loads only the China outline and four pulsing demo polygons; point data loads only after a polygon click.
- Clicking a polygon displays only points whose centers fall inside that polygon; the audited real counts are 2,471, 8,702, 4,392, and 3,735, with 32 unassigned and zero overlapping points.
- Default scenario is `current`; current color is `#16A34A`, future color is `#2563EB`.
- All four metrics use unit `thousand_usd` and display label `千美元`; cards show metric values to two decimals and coordinates to six decimals.
- The supplied workbook’s seventh header is a duplicate `EV` (semantically the future `EV.1` column); the builder accepts only this exact duplicate-`EV` source variant or the canonical `EV.1` spelling and normalizes both to `future.reclamationValue`.
- The legend has four reclamation-value classes: hollow `不可复耕`; valid values `0-5` labeled `一般复耕区`, `5-10` labeled `建议复耕区`, and values `>10` labeled `优先复耕区`.
- A scenario is non-reclaimable only when all four metrics equal `-999`; mixed `-999`/finite metrics block the build.
- Each circle represents about 1 km²: geographic radius is 564.19 m, clamped to a minimum screen radius of 3 px.
- Point rendering uses one `ReclamationCanvasLayer` React/Leaflet overlay component with base and transient highlight canvases; it must not create one React, SVG, or Leaflet layer per point.
- Scenario switching is local and must not issue another HTTP request; switching clears the selected point card.
- Preserve all unrelated user worktree changes. Stage and commit only the files listed by each task.

## File Structure

### Data build and backend

- Create `scripts/build_reclamation_data.py`: source validation, spatial assignment, deterministic artifact generation, China dissolve/simplify, CLI.
- Create `backend/tests/test_build_reclamation.py`: builder unit and artifact contract tests.
- Modify `backend/requirements.txt`: add build-time `openpyxl` and `shapely` dependencies available to CI.
- Create `data/reclamation/`: generated manifest, overview, GeoJSON, raw point JSON, and precompressed point JSON.
- Create `backend/reclamation_data.py`: safe artifact lookup and raw/gzip response selection.
- Create `backend/routers/reclamation.py`: overview and region-point endpoints.
- Create `backend/tests/test_reclamation.py`: endpoint, cache, gzip, absence, and corruption tests.
- Modify `backend/main.py`: register the reclamation router under `/api`.

### Frontend

- Modify `frontend/src/types/index.ts`: reclamation wire and named domain types.
- Modify `frontend/src/services/api.ts`: overview request, abortable point request, and tuple parser.
- Modify `frontend/src/test/api.test.ts`: API request and tuple mapping tests.
- Create `frontend/src/components/reclamationCanvas.ts`: pure scenario, radius, screen-index, hit-test, and draw functions.
- Create `frontend/src/test/reclamationCanvas.test.ts`: pure Canvas engine tests.
- Create `frontend/src/components/ReclamationCanvasLayer.tsx`: Leaflet lifecycle plus two-canvas rendering surface.
- Create `frontend/src/test/ReclamationCanvasLayer.test.tsx`: lifecycle and interaction tests with a fake map.
- Create `frontend/src/components/ReclamationMap.tsx`: map, base tile, China outline, demo polygons, view controller, Canvas child.
- Create `frontend/src/test/ReclamationMap.test.tsx`: overview styling, selection, fitBounds, and Canvas wiring tests.
- Create `frontend/src/components/ScenarioSwitch.tsx`: accessible current/future controls.
- Create `frontend/src/components/ReclamationLegend.tsx`: scenario/status/scale legend.
- Create `frontend/src/components/ReclamationInfoCard.tsx`: selected-point metric card.
- Create `frontend/src/pages/ReclamationPage.tsx`: load/cache/abort/retry/drill-down state machine.
- Create `frontend/src/test/ReclamationPage.test.tsx`: page state and interaction tests.
- Modify `frontend/src/App.tsx`: route `/reclamation` to `ReclamationPage`.
- Modify `frontend/src/test/App.test.tsx`: route integration assertion and API mocks.
- Modify `frontend/src/App.css`: reclamation layout, pulse, controls, cards, legend, Canvas, reduced-motion, and responsive rules.

---

### Task 1: Validate and spatially assign reclamation source rows

**Files:**
- Create: `scripts/build_reclamation_data.py`
- Create: `backend/tests/test_build_reclamation.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: `.xlsx` with columns `longitude`, `latitude`, `EV`, `optimal_irr`, `optimal_npp`, `optimal_soc`, followed by either canonical `EV.1` or the supplied file’s duplicate `EV`, then `irr`, `npp`, `soc`; region GeoJSON features with `WRRCD` and `WRRNM`.
- Produces: `SourcePoint`, `ScenarioMetrics`, `RegionAssignment`, `read_workbook_points(path)`, `normalize_region_features(features)`, and `assign_points(points, regions)` for Task 2.

- [ ] **Step 1: Add build dependencies and write failing parsing/validation tests**

Append these exact constraints to `backend/requirements.txt`:

```text
openpyxl>=3.1,<4
shapely>=2.0,<3
```

Create tests that build a real temporary workbook and exercise the desired public functions:

```python
from openpyxl import Workbook
import pytest

from scripts.build_reclamation_data import (
    EXPECTED_COLUMNS,
    assign_points,
    normalize_region_features,
    read_workbook_points,
)


def write_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "pixel_values"
    sheet.append(EXPECTED_COLUMNS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def test_read_workbook_maps_both_scenarios_and_rejects_mixed_nodata(tmp_path):
    source = tmp_path / "values.xlsx"
    write_workbook(source, [[105.0, 38.0, 1, 2, 3, 4, -999, -999, -999, -999]])

    points = read_workbook_points(source)

    assert points[0].current.as_tuple() == (1.0, 2.0, 3.0, 4.0)
    assert points[0].future.as_tuple() == (-999.0, -999.0, -999.0, -999.0)

    write_workbook(source, [[105.0, 38.0, 1, -999, 3, 4, 5, 6, 7, 8]])
    with pytest.raises(ValueError, match="row 2.*mixed -999"):
        read_workbook_points(source)


def test_assign_points_uses_polygon_centers_and_audits_outside_points():
    regions = normalize_region_features([
        {
            "type": "Feature",
            "properties": {"WRRCD": "A", "WRRNM": "区域A"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[100, 30], [102, 30], [102, 32], [100, 32], [100, 30]]],
            },
        },
    ])
    points = [
        make_point(101.0, 31.0),
        make_point(110.0, 40.0),
    ]

    result = assign_points(points, regions)

    assert [point.longitude for point in result.by_region["A"]] == [101.0]
    assert result.unassigned_indexes == [1]
    assert result.overlapping_indexes == []
```

Define `make_point()` in the test using `SourcePoint` and `ScenarioMetrics`, both with finite current/future values.

- [ ] **Step 2: Run tests and verify RED**

Run in PowerShell from the repository root:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_build_reclamation.py -v -p no:cacheprovider
```

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.build_reclamation_data'`.

- [ ] **Step 3: Implement minimal typed parsing, validation, and assignment**

Implement these exact public contracts in `scripts/build_reclamation_data.py`:

```python
EXPECTED_COLUMNS = [
    "longitude", "latitude",
    "EV", "optimal_irr", "optimal_npp", "optimal_soc",
    "EV.1", "irr", "npp", "soc",
]
NODATA = -999.0

@dataclass(frozen=True)
class ScenarioMetrics:
    reclamation_value: float
    water_consumption: float
    yield_value: float
    soil_carbon_value: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (
            self.reclamation_value,
            self.water_consumption,
            self.yield_value,
            self.soil_carbon_value,
        )

@dataclass(frozen=True)
class SourcePoint:
    longitude: float
    latitude: float
    current: ScenarioMetrics
    future: ScenarioMetrics

@dataclass(frozen=True)
class DemoRegion:
    region_id: str
    name: str
    feature: dict

@dataclass(frozen=True)
class RegionAssignment:
    by_region: dict[str, list[SourcePoint]]
    unassigned_indexes: list[int]
    overlapping_indexes: list[int]
```

Use `openpyxl.load_workbook(path, read_only=True, data_only=True)`, require one `pixel_values` sheet, require the exact header order, reject booleans/non-finite values, validate longitude in `[-180, 180]` and latitude in `[-90, 90]`, reject duplicate coordinate pairs, and include the 1-based workbook row in every validation error. A scenario is valid when all four values equal `NODATA` or none equals `NODATA`.

Normalize `WRRCD`/`WRRNM` into `properties.id`/`properties.name`, reject duplicate or empty IDs/names, and call the existing `scripts.build_township_chunks.point_in_geometry((lng, lat), geometry)` for center-in-polygon assignment. Add an index to `overlapping_indexes` when more than one region matches, while retaining the point in every matching bucket for the audit to detect.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the same pytest command. Expected: all tests in `test_build_reclamation.py` pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add backend/requirements.txt backend/tests/test_build_reclamation.py scripts/build_reclamation_data.py
git commit -m "feat: validate reclamation source data"
```

### Task 2: Generate deterministic region artifacts and the China overview

**Files:**
- Modify: `scripts/build_reclamation_data.py`
- Modify: `backend/tests/test_build_reclamation.py`
- Create: `data/reclamation/manifest.json`
- Create: `data/reclamation/overview.json`
- Create: `data/reclamation/overview.json.gz`
- Create: `data/reclamation/regions.geojson`
- Create: `data/reclamation/china_outline.geojson`
- Create: `data/reclamation/points/D030300.json`
- Create: `data/reclamation/points/D030300.json.gz`
- Create: `data/reclamation/points/D030400.json`
- Create: `data/reclamation/points/D030400.json.gz`
- Create: `data/reclamation/points/D030500.json`
- Create: `data/reclamation/points/D030500.json.gz`
- Create: `data/reclamation/points/D080100.json`
- Create: `data/reclamation/points/D080100.json.gz`

**Interfaces:**
- Consumes: Task 1 models/functions plus a county Shapefile.
- Produces: `build_china_outline(features, tolerance=0.05)`, `build_reclamation_data(workbook, regions_shp, counties_shp, output, force) -> dict`, schema version `1`, deterministic raw/gzip files, and manifest counts consumed by Task 3.

- [ ] **Step 1: Write failing artifact tests**

Add tests for exact tuple order, topology-preserving China output, deterministic gzip, and atomic audit behavior:

```python
def test_build_outputs_compact_tuples_manifest_and_deterministic_gzip(monkeypatch, tmp_path):
    workbook_path = tmp_path / "values.xlsx"
    regions_path = tmp_path / "regions.shp"
    counties_path = tmp_path / "counties.shp"
    output_path = tmp_path / "output"
    for path in (workbook_path, regions_path, counties_path):
        path.touch()
    monkeypatch.setattr(builder, "read_workbook_points", lambda _path: [make_point(101, 31)])
    monkeypatch.setattr(builder, "read_demo_regions", lambda _path: [square_region("A", "区域A")])
    monkeypatch.setattr(builder, "read_county_features", lambda _path: [square_feature(70, 15, 140, 55)])

    result = builder.build_reclamation_data(
        workbook_path,
        regions_path,
        counties_path,
        output_path,
        force=False,
    )

    payload = json.loads((tmp_path / "output/points/A.json").read_text(encoding="utf-8"))
    assert payload["points"][0] == [101.0, 31.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    assert result["inputPointCount"] == 1
    assert result["assignedPointCount"] == 1
    raw = (tmp_path / "output/points/A.json").read_bytes()
    assert gzip.decompress((tmp_path / "output/points/A.json.gz").read_bytes()) == raw
    first_gzip = (tmp_path / "output/points/A.json.gz").read_bytes()

    shutil.rmtree(tmp_path / "output")
    builder.build_reclamation_data(
        workbook_path,
        regions_path,
        counties_path,
        output_path,
        force=False,
    )
    assert (tmp_path / "output/points/A.json.gz").read_bytes() == first_gzip
```

Above this test, define `square_feature(min_x, min_y, max_x, max_y)` to return a closed Polygon feature and `square_region(region_id, name)` to wrap the same geometry in `DemoRegion`. Import `gzip`, `json`, `shutil`, and `scripts.build_reclamation_data as builder`. Add separate assertions that `build_china_outline()` returns Polygon/MultiPolygon, simplifies with `preserve_topology=True`, and the serialized outline is below 1,000,000 bytes.

- [ ] **Step 2: Run focused tests and verify RED**

Run the Task 1 pytest command. Expected: FAIL because `build_reclamation_data` and `build_china_outline` are not defined.

- [ ] **Step 3: Implement deterministic artifacts and CLI**

Implement the following stable formats:

```python
SCHEMA_VERSION = 1
POINT_FIELDS = [
    "longitude", "latitude",
    "current.reclamationValue", "current.waterConsumption",
    "current.yieldValue", "current.soilCarbonValue",
    "future.reclamationValue", "future.waterConsumption",
    "future.yieldValue", "future.soilCarbonValue",
]

def compact_point(point: SourcePoint) -> list[float]:
    return [
        round(point.longitude, 6), round(point.latitude, 6),
        *(round(value, 6) for value in point.current.as_tuple()),
        *(round(value, 6) for value in point.future.as_tuple()),
    ]

def encode_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

def encode_gzip(raw: bytes) -> bytes:
    return gzip.compress(raw, compresslevel=6, mtime=0)
```

Use `shapely.geometry.shape`, `mapping`, and `shapely.ops.unary_union` to dissolve counties, then `simplify(0.05, preserve_topology=True)`. Write `overview.json` with `{schemaVersion, unit, metrics, chinaOutline, regions}`, where `regions` is a GeoJSON FeatureCollection, and each point file with `{schemaVersion, region, unit, fields, points}`. Compute every region's bounds as `[[minLatitude, minLongitude], [maxLatitude, maxLongitude]]`. Include SHA-256 values for the workbook and every `.shp/.shx/.dbf/.prj/.cpg` sidecar that exists. Set manifest `builtAt` to the UTC ISO-8601 timestamp of the newest source-file modification time so identical inputs produce identical output. Reject any overlap, but permit audited unassigned points. Stage output in a temporary sibling directory and replace the target only after every validation and size check passes.

Expose this CLI:

```powershell
python scripts/build_reclamation_data.py `
  --workbook "C:\Users\Administrator\Desktop\复耕潜力数据\values..xlsx" `
  --regions-shp "C:\Users\Administrator\Desktop\复耕潜力数据\示范区域范围\Export_Output.shp" `
  --counties-shp "F:\矢量底图\中国_县\中国_县.shp" `
  --output "data\reclamation" `
  --force
```

- [ ] **Step 4: Run tests, build real artifacts, and verify counts**

Run focused pytest; then run the CLI above. Verify with:

```powershell
$manifest = Get-Content -Raw 'data\reclamation\manifest.json' | ConvertFrom-Json
$manifest.inputPointCount
$manifest.assignedPointCount
$manifest.unassignedPointCount
$manifest.overlappingPointCount
$manifest.regions | Select-Object id,name,pointCount
```

Expected: `19332`, `19300`, `32`, `0`; region counts match `2471`, `8702`, `4392`, `3735`; every `.json.gz` decompresses byte-for-byte to its `.json`; `china_outline.geojson` is below 1 MB.

- [ ] **Step 5: Commit Task 2**

```powershell
git add scripts/build_reclamation_data.py backend/tests/test_build_reclamation.py data/reclamation
git commit -m "feat: build reclamation map artifacts"
```

### Task 3: Serve overview and points as cached raw/gzip artifacts

**Files:**
- Create: `backend/reclamation_data.py`
- Create: `backend/routers/reclamation.py`
- Create: `backend/tests/test_reclamation.py`
- Modify: `backend/main.py`

**Interfaces:**
- Consumes: Task 2 `data/reclamation` schema version `1` artifacts.
- Produces: `GET /api/reclamation/regions` and `GET /api/reclamation/points/{region_id}`.

- [ ] **Step 1: Write failing endpoint tests**

Create a temporary artifact root containing `manifest.json`, `overview.json(.gz)`, and `points/A.json(.gz)`, monkeypatch `reclamation_router.RECLAMATION_ROOT`, then assert:

```python
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

def test_reclamation_points_reject_unknown_and_corrupt_artifacts(monkeypatch, artifact_root):
    monkeypatch.setattr(reclamation_router, "RECLAMATION_ROOT", artifact_root)
    assert client.get("/api/reclamation/points/../../secret").status_code == 404
    assert client.get("/api/reclamation/points/UNKNOWN").status_code == 404
    (artifact_root / "manifest.json").write_text("{broken", encoding="utf-8")
    assert client.get("/api/reclamation/regions").status_code == 500
```

- [ ] **Step 2: Run endpoint tests and verify RED**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_reclamation.py -v -p no:cacheprovider
```

Expected: collection fails because `backend.routers.reclamation` does not exist.

- [ ] **Step 3: Implement safe representation lookup and routes**

In `backend/reclamation_data.py`, implement:

```python
SCHEMA_VERSION = 1

def load_manifest(root: Path) -> dict:
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Unsupported reclamation schema version")
    return data

def region_ids(root: Path) -> set[str]:
    return {str(region["id"]) for region in load_manifest(root)["regions"]}

def choose_representation(root: Path, relative_json: Path, accept_encoding: str) -> tuple[Path, dict[str, str]]:
    raw = (root / relative_json).resolve()
    if root.resolve() not in raw.parents or not raw.is_file():
        raise FileNotFoundError(relative_json)
    gzip_path = raw.with_suffix(raw.suffix + ".gz")
    headers = {"Vary": "Accept-Encoding"}
    if "gzip" in accept_encoding.lower() and gzip_path.is_file():
        headers["Content-Encoding"] = "gzip"
        return gzip_path, headers
    return raw, headers
```

In `backend/routers/reclamation.py`, map missing/unknown artifacts to 404 and malformed/unsupported manifests to 500, then return `FileResponse(path, media_type="application/json", headers={**representation_headers, "Cache-Control": cache_control})`. Set `cache_control` to `public, max-age=300` for overview and `public, max-age=86400` for point files. Import and register the router in `backend/main.py` under `/api`.

- [ ] **Step 4: Run focused and existing backend endpoint tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_reclamation.py backend/tests/test_irrigation.py backend/tests/test_township_vector_api.py -v -p no:cacheprovider
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add backend/reclamation_data.py backend/routers/reclamation.py backend/tests/test_reclamation.py backend/main.py
git commit -m "feat: serve reclamation map data"
```

### Task 4: Add typed frontend API parsing and abortable requests

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/test/api.test.ts`

**Interfaces:**
- Consumes: Task 3 wire responses.
- Produces: `getReclamationOverview(signal?)`, `getReclamationPoints(regionId, signal?)`, `parseReclamationPointTuple(tuple)`, and named TypeScript domain objects consumed by Tasks 6–8.

- [ ] **Step 1: Write failing tuple and request tests**

Extend the hoisted Axios `clientGet` tests with:

```typescript
describe('reclamation API helpers', () => {
  it('maps the compact point tuple into named current and future metrics', async () => {
    clientGet.mockResolvedValueOnce({
      data: {
        schemaVersion: 1,
        region: { id: 'A', name: '区域A' },
        unit: 'thousand_usd',
        fields: [],
        points: [[101, 31, 1, 2, 3, 4, 5, 6, 7, 8]],
      },
    })
    const controller = new AbortController()

    const result = await getReclamationPoints('A', controller.signal)

    expect(clientGet).toHaveBeenCalledWith('/reclamation/points/A', {
      signal: controller.signal,
    })
    expect(result.points[0]).toEqual({
      id: 'A:0',
      longitude: 101,
      latitude: 31,
      current: {
        reclamationValue: 1,
        waterConsumption: 2,
        yieldValue: 3,
        soilCarbonValue: 4,
      },
      future: {
        reclamationValue: 5,
        waterConsumption: 6,
        yieldValue: 7,
        soilCarbonValue: 8,
      },
    })
  })

  it('rejects malformed tuples before page state sees them', async () => {
    clientGet.mockResolvedValueOnce({
      data: {
        schemaVersion: 1,
        region: { id: 'A', name: '区域A' },
        unit: 'thousand_usd',
        fields: [],
        points: [[101, 31, 1]],
      },
    })
    await expect(getReclamationPoints('A')).rejects.toThrow('10 numeric values')
  })
})
```

Add `getReclamationOverview` to the same describe block and assert `clientGet('/reclamation/regions', { signal })`.

- [ ] **Step 2: Run API tests and verify RED**

```powershell
npm --prefix frontend run test -- src/test/api.test.ts
```

Expected: TypeScript/Vitest fails because the reclamation functions and types do not exist.

- [ ] **Step 3: Add exact wire/domain types and parser**

Add these contracts to `frontend/src/types/index.ts`:

```typescript
export type ReclamationScenario = 'current' | 'future'
export type ReclamationUnit = 'thousand_usd'

export interface ReclamationMetrics {
  reclamationValue: number
  waterConsumption: number
  yieldValue: number
  soilCarbonValue: number
}

export interface ReclamationPoint {
  id: string
  longitude: number
  latitude: number
  current: ReclamationMetrics
  future: ReclamationMetrics
}

export type ReclamationPointTuple = [
  number, number, number, number, number,
  number, number, number, number, number,
]

export interface ReclamationRegionProperties {
  id: string
  name: string
  pointCount: number
  /** Leaflet order: [[south, west], [north, east]]. */
  bounds: [[number, number], [number, number]]
}

export interface ReclamationFeature<P> {
  type: 'Feature'
  properties: P
  geometry: { type: string; coordinates: unknown }
}

export interface ReclamationFeatureCollection<P> {
  type: 'FeatureCollection'
  features: ReclamationFeature<P>[]
}
```

Define overview/wire/domain response interfaces around these types. In `api.ts`, URL-encode `regionId`, require exactly 10 finite numeric tuple entries, reject mixed `-999`/finite values within either scenario, assign stable point IDs `${regionId}:${index}`, and pass `{ signal }` to Axios. The parser preserves all-four-`-999` scenarios for hollow-circle rendering.

- [ ] **Step 4: Run API tests and verify GREEN**

Run the Task 4 Vitest command. Expected: all `api.test.ts` tests pass.

- [ ] **Step 5: Commit Task 4**

```powershell
git add frontend/src/types/index.ts frontend/src/services/api.ts frontend/src/test/api.test.ts
git commit -m "feat: add reclamation API contracts"
```

### Task 5: Implement the pure Canvas rendering and hit-test engine

**Files:**
- Create: `frontend/src/components/reclamationCanvas.ts`
- Create: `frontend/src/test/reclamationCanvas.test.ts`

**Interfaces:**
- Consumes: `ReclamationPoint`, `ReclamationScenario`, and a projected `{x, y}` per point.
- Produces: `scenarioMetrics`, `isReclaimable`, `circleRadiusPixels`, `buildScreenIndex`, `hitTestScreenIndex`, `drawBasePoints`, and `drawHoverPoint` for Task 6.

- [ ] **Step 1: Write failing behavior tests**

Cover nodata semantics, radius clamping, nearest-hit selection, and Canvas styles:

```typescript
it('treats only four -999 metrics as non-reclaimable', () => {
  expect(isReclaimable(nodataMetrics)).toBe(false)
  expect(isReclaimable(finiteMetrics)).toBe(true)
})

it('uses a 564.19 m radius with a 3 px minimum', () => {
  expect(circleRadiusPixels(40, 4)).toBe(3)
  expect(circleRadiusPixels(40, 12)).toBeGreaterThan(3)
})

it('finds the nearest reclaimable point in the current and adjacent 32 px buckets', () => {
  const index = buildScreenIndex([
    screenPoint(0, 31, 31, true),
    screenPoint(1, 34, 31, true),
    screenPoint(2, 32, 32, false),
  ])
  expect(hitTestScreenIndex(index, 33, 31)).toBe(1)
  expect(hitTestScreenIndex(index, 32, 32, { reclaimableOnly: true })).not.toBe(2)
})

it('draws current valid points filled green and nodata points hollow', () => {
  const context = fakeCanvasContext()
  drawBasePoints(context, projectedFixture, 'current', '#16A34A')
  expect(context.fill).toHaveBeenCalledTimes(1)
  expect(context.stroke).toHaveBeenCalledTimes(2)
})
```

In the test file define `nodataMetrics` with four `-999` values, `finiteMetrics` with values `1, 2, 3, 4`, and `screenPoint(sourceIndex, x, y, reclaimable)` returning radius `4`. Define `fakeCanvasContext()` as an object whose `beginPath`, `arc`, `fill`, `stroke`, and `clearRect` members are `vi.fn()`, cast through `unknown` to `CanvasRenderingContext2D`. Define `projectedFixture` with one reclaimable and one non-reclaimable `ScreenPoint`.

- [ ] **Step 2: Run Canvas engine tests and verify RED**

```powershell
npm --prefix frontend run test -- src/test/reclamationCanvas.test.ts
```

Expected: FAIL because `reclamationCanvas.ts` does not exist.

- [ ] **Step 3: Implement the minimal pure engine**

Use these constants and formulas:

```typescript
export const RECLAMATION_RADIUS_METERS = 564.19
export const MIN_RADIUS_PX = 3
export const SCREEN_BUCKET_PX = 32
const EARTH_PIXEL_METERS_AT_ZOOM_ZERO = 156543.03392

export function metersPerPixel(latitude: number, zoom: number): number {
  return EARTH_PIXEL_METERS_AT_ZOOM_ZERO
    * Math.cos(latitude * Math.PI / 180)
    / 2 ** zoom
}

export function circleRadiusPixels(latitude: number, zoom: number): number {
  return Math.max(
    MIN_RADIUS_PX,
    RECLAMATION_RADIUS_METERS / metersPerPixel(latitude, zoom),
  )
}
```

Define `ScreenPoint` with `{sourceIndex, x, y, radius, reclaimable}` and `ScreenIndex` with a `Map<string, ScreenPoint[]>`. Bucket by `Math.floor(coordinate / 32)`. Hit-test the nine neighboring buckets, ignore candidates outside `Math.max(candidate.radius, 5)`, and choose the smallest squared distance, breaking ties by lower `sourceIndex`.

`drawBasePoints()` must set fill alpha to `0.76`, stroke alpha to `0.95`, and line width to `1.25`; nodata points call `stroke()` without `fill()`. `drawHoverPoint()` clears the transient canvas and draws one reclaimable point with radius `baseRadius + 2`, a white 3 px outer stroke, and the scenario color inner stroke. Neither function creates DOM nodes or performs projection.

- [ ] **Step 4: Run Canvas engine tests and verify GREEN**

Run the Task 5 Vitest command. Expected: all tests pass.

- [ ] **Step 5: Commit Task 5**

```powershell
git add frontend/src/components/reclamationCanvas.ts frontend/src/test/reclamationCanvas.test.ts
git commit -m "feat: add reclamation canvas engine"
```

### Task 6: Mount one Leaflet Canvas overlay with hover and click interaction

**Files:**
- Create: `frontend/src/components/ReclamationCanvasLayer.tsx`
- Create: `frontend/src/test/ReclamationCanvasLayer.test.tsx`

**Interfaces:**
- Consumes: Task 4 named points and Task 5 pure engine.
- Produces: `<ReclamationCanvasLayer points scenario color onPointSelect />`, with no per-point React/Leaflet/SVG children. Its wrapper carries both `data-reclamation-canvas-layer` and `data-testid="reclamation-canvas-layer"`.

- [ ] **Step 1: Write failing overlay lifecycle and interaction tests**

Mock `useMap()` with a stable fake map that supplies `getPane('overlayPane')`, `getContainer()`, `getSize()`, `getZoom()`, `latLngToContainerPoint()`, `on()`, and `off()`. Stub `HTMLCanvasElement.prototype.getContext` with the Task 5 fake context. Assert:

```typescript
it('mounts exactly one overlay wrapper with base and highlight canvases', () => {
  const { unmount } = render(
    <ReclamationCanvasLayer
      points={pointFixture}
      scenario="current"
      color="#16A34A"
      onPointSelect={onPointSelect}
    />,
  )

  expect(overlayPane.querySelectorAll('[data-reclamation-canvas-layer]')).toHaveLength(1)
  expect(overlayPane.querySelectorAll('canvas')).toHaveLength(2)
  expect(overlayPane.querySelectorAll('svg')).toHaveLength(0)
  unmount()
  expect(overlayPane.querySelectorAll('canvas')).toHaveLength(0)
})

it('highlights and selects only reclaimable points', () => {
  renderCanvasLayer()
  mapContainer.dispatchEvent(mouseEventAt('mousemove', 100, 80))
  mapContainer.dispatchEvent(mouseEventAt('click', 100, 80))
  expect(onPointSelect).toHaveBeenCalledWith(pointFixture[0])

  mapContainer.dispatchEvent(mouseEventAt('click', 200, 80))
  expect(onPointSelect).toHaveBeenCalledTimes(1)
})
```

Also assert that `moveend`, `zoomend`, and `resize` handlers are removed on unmount and that switching `scenario` redraws without adding canvases.

- [ ] **Step 2: Run overlay tests and verify RED**

```powershell
npm --prefix frontend run test -- src/test/ReclamationCanvasLayer.test.tsx
```

Expected: FAIL because `ReclamationCanvasLayer.tsx` does not exist.

- [ ] **Step 3: Implement the overlay lifecycle**

Use `useMap()` and one effect to create a `div[data-reclamation-canvas-layer][data-testid="reclamation-canvas-layer"]` containing two absolutely positioned canvases. Set the wrapper and canvases to `pointer-events: none`; listen on the Leaflet map container so polygon clicking remains available. Size the wrapper to the map and align it with `L.DomUtil.setPosition(wrapper, map.containerPointToLayerPoint([0, 0]))`. On redraw:

```typescript
const size = map.getSize()
for (const canvas of [baseCanvas, hoverCanvas]) {
  canvas.width = Math.max(1, Math.round(size.x * devicePixelRatio))
  canvas.height = Math.max(1, Math.round(size.y * devicePixelRatio))
  canvas.style.width = `${size.x}px`
  canvas.style.height = `${size.y}px`
  canvas.getContext('2d')?.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
}
const projected = points.map((point, sourceIndex) => {
  const screen = map.latLngToContainerPoint([point.latitude, point.longitude])
  const metrics = scenarioMetrics(point, scenario)
  return {
    sourceIndex,
    x: screen.x,
    y: screen.y,
    radius: circleRadiusPixels(point.latitude, map.getZoom()),
    reclaimable: isReclaimable(metrics),
  }
})
```

Draw the base once, rebuild the 32 px index, and clear the hover surface. Throttle mousemove work with one `requestAnimationFrame`; only redraw the transient canvas when the hovered index changes. Set the map container cursor to `pointer` only over reclaimable points and restore the prior cursor on leave/unmount. The click listener calls `onPointSelect(points[index])`. Clean up DOM, events, cursor, and pending animation frames.

- [ ] **Step 4: Run overlay plus pure engine tests**

```powershell
npm --prefix frontend run test -- src/test/reclamationCanvas.test.ts src/test/ReclamationCanvasLayer.test.tsx
```

Expected: all selected tests pass with no jsdom canvas warnings.

- [ ] **Step 5: Commit Task 6**

```powershell
git add frontend/src/components/ReclamationCanvasLayer.tsx frontend/src/test/ReclamationCanvasLayer.test.tsx
git commit -m "feat: render reclamation points on canvas"
```

### Task 7: Build the China overview and demo-region drill-down map

**Files:**
- Create: `frontend/src/components/ReclamationMap.tsx`
- Create: `frontend/src/test/ReclamationMap.test.tsx`

**Interfaces:**
- Consumes: Task 4 overview types and Task 6 Canvas layer; Task 8 later supplies the state through props.
- Produces: `<ReclamationMap overview selectedRegion points scenario onRegionSelect onPointSelect />`.

- [ ] **Step 1: Write failing map composition tests**

Mock `MapContainer`, `TileLayer`, `GeoJSON`, `Pane`, and `useMap`. Capture each GeoJSON's `data`, `style`, and `onEachFeature` callback. Assert:

```typescript
it('shows China and four pulsing demo polygons before selection', () => {
  render(<ReclamationMap {...overviewProps} selectedRegion={null} points={[]} />)
  expect(geoJsonLayers).toHaveLength(2)
  expect(geoJsonLayers[0].data).toEqual(overview.chinaOutline)
  expect(geoJsonLayers[1].data.features).toHaveLength(4)
  expect(geoJsonLayers[1].style(overview.regions.features[0]).className)
    .toContain('reclamation-region-pulse')
  expect(screen.queryByTestId('reclamation-canvas-layer')).not.toBeInTheDocument()
})

it('fits the clicked region and mounts one canvas layer after data arrives', () => {
  render(<ReclamationMap {...detailProps} />)
  expect(fakeMap.fitBounds).toHaveBeenCalledWith(
    [[37.2, 104.6], [41.8, 112.8]],
    expect.objectContaining({ padding: [32, 32], animate: true }),
  )
  expect(screen.getByTestId('reclamation-canvas-layer')).toBeInTheDocument()
})
```

Trigger the region feature's click handler and assert `onRegionSelect` receives the typed `id`, `name`, `pointCount`, and `bounds`.

- [ ] **Step 2: Run map tests and verify RED**

```powershell
npm --prefix frontend run test -- src/test/ReclamationMap.test.tsx
```

Expected: FAIL because `ReclamationMap.tsx` does not exist.

- [ ] **Step 3: Implement map composition and view controller**

Use the same Esri World Street Map URL as `MapView.tsx`, `center={[35.5, 104]}`, `zoom={4}`, `minZoom={3}`, `maxZoom={14}`, and the existing China max bounds. Render the China outline in a pane below the demo polygons with neutral `#475569` 1.5 px stroke and no fill. In overview mode render all demo polygons with fill `#F97316`, fill opacity `0.62`, stroke `#FFF7ED`, and class `reclamation-region-pulse`.

When selected, render only the selected polygon with transparent fill, stroke `#F97316`, and weight `3`. A `ReclamationViewController` child calls `fitBounds` with the selected region bounds and 32 px padding; when selection becomes null, call `fitBounds([[15, 73], [54, 135]], {padding: [20, 20], animate: true})`. Mount `ReclamationCanvasLayer` only when both a selected region and non-empty points exist.

- [ ] **Step 4: Run map and Canvas tests**

```powershell
npm --prefix frontend run test -- src/test/ReclamationMap.test.tsx src/test/ReclamationCanvasLayer.test.tsx src/test/reclamationCanvas.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 7**

```powershell
git add frontend/src/components/ReclamationMap.tsx frontend/src/test/ReclamationMap.test.tsx
git commit -m "feat: add reclamation drill-down map"
```

### Task 8: Implement page state, controls, cards, route, styling, and final verification

**Files:**
- Create: `frontend/src/components/ScenarioSwitch.tsx`
- Create: `frontend/src/components/ReclamationLegend.tsx`
- Create: `frontend/src/components/ReclamationInfoCard.tsx`
- Create: `frontend/src/pages/ReclamationPage.tsx`
- Create: `frontend/src/test/ReclamationPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/test/App.test.tsx`
- Modify: `frontend/src/App.css`

**Interfaces:**
- Consumes: Tasks 4 and 7.
- Produces: complete `/reclamation` user flow and responsive presentation.

- [ ] **Step 1: Write failing page-state and route tests**

Mock `getReclamationOverview`, `getReclamationPoints`, and `ReclamationMap`. The map mock exposes buttons that call `onRegionSelect` and `onPointSelect`; the page itself renders the real `返回全国` button. Cover these behaviors in separate tests:

```typescript
it('loads only the overview and defaults to current after a region click', async () => {
  render(<ReclamationPage />)
  expect(await screen.findByText('点击高亮区域查看复耕潜力')).toBeInTheDocument()
  expect(apiMocks.getReclamationPoints).not.toHaveBeenCalled()

  await user.click(screen.getByRole('button', { name: '选择区域A' }))
  expect(apiMocks.getReclamationPoints).toHaveBeenCalledWith('A', expect.any(AbortSignal))
  expect(await screen.findByRole('button', { name: '当前情景' })).toHaveAttribute('aria-pressed', 'true')
})

it('switches scenarios locally and closes the old point card', async () => {
  await renderLoadedRegionAndSelectPoint()
  expect(screen.getByText('1.00 千美元')).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: '未来情景' }))

  expect(apiMocks.getReclamationPoints).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('heading', { name: '点位信息' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '未来情景' })).toHaveAttribute('aria-pressed', 'true')
})

it('aborts stale region requests and reuses successful cached regions', async () => {
  const first = deferred<ReclamationPointsResponse>()
  const second = deferred<ReclamationPointsResponse>()
  apiMocks.getReclamationPoints.mockImplementation((id, signal) => {
    observedSignals.set(id, signal)
    return id === 'A' ? first.promise : second.promise
  })
  render(<ReclamationPage />)
  await selectRegion('A')
  await selectRegion('B')
  expect(observedSignals.get('A')?.aborted).toBe(true)
  second.resolve(pointsFor('B'))
  first.resolve(pointsFor('A'))
  expect(await screen.findByText('区域B')).toBeInTheDocument()

  await backAndSelectRegion('B')
  expect(apiMocks.getReclamationPoints).toHaveBeenCalledTimes(2)
})
```

Add tests for overview retry, point retry while retaining the selected border, non-reclaimable point not opening the card, two-decimal metrics, six-decimal coordinates, scale legend text, and returning to overview. In `App.test.tsx`, navigate to `/reclamation` and assert the new heading appears and the old text `该板块暂未实现。` does not.

- [ ] **Step 2: Run page and app tests and verify RED**

```powershell
npm --prefix frontend run test -- src/test/ReclamationPage.test.tsx src/test/App.test.tsx
```

Expected: FAIL because the page/components and route do not exist.

- [ ] **Step 3: Implement the page state machine and focused UI components**

`ReclamationPage` must own:

```typescript
const [overview, setOverview] = useState<ReclamationOverviewResponse | null>(null)
const [overviewStatus, setOverviewStatus] = useState<'loading' | 'ready' | 'error'>('loading')
const [selectedRegion, setSelectedRegion] = useState<ReclamationRegionProperties | null>(null)
const [pointsState, setPointsState] = useState<
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: ReclamationPointsResponse }
>({ status: 'idle' })
const [scenario, setScenario] = useState<ReclamationScenario>('current')
const [selectedPoint, setSelectedPoint] = useState<ReclamationPoint | null>(null)
const cacheRef = useRef(new Map<string, ReclamationPointsResponse>())
const requestRef = useRef<{ id: number; controller: AbortController } | null>(null)
```

On region selection, abort the prior controller, increment request ID, clear the card, reset to `current`, use the cache if present, otherwise call `getReclamationPoints(id, signal)`. Ignore `AbortError`/Axios cancellation and any response with an obsolete request ID. On point selection, defensively call `isReclaimable(scenarioMetrics(point, scenario))` before opening the card. On scenario change clear `selectedPoint`; on return abort pending work, clear selection/points/card, and retain the cache.

`ScenarioSwitch` uses two buttons with `aria-pressed`. `ReclamationLegend` renders the current scenario color plus four value classes: hollow `不可复耕`, `0-5 一般复耕区`, `5-10 建议复耕区`, and `>10 优先复耕区`, followed by `每个圆代表约 1 km × 1 km 范围`. `ReclamationInfoCard` uses `<dl>`, formats metrics with `toFixed(2)` and the `千美元` label, coordinates with `toFixed(6)`, and has an accessible `关闭点位信息` button. Add `aria-live="polite"` to loading/retry state text.

Replace only the `/reclamation` route's placeholder with `<ReclamationPage />`; keep the water-demand placeholder import/use intact.

- [ ] **Step 4: Add the approved visual and responsive CSS**

Add scoped `.reclamation-*` rules to `App.css`: full-height map page, absolute overview instruction, top-left scenario switch, top-right info card, bottom-right legend, orange polygon pulse, loading/error overlay, and Canvas wrapper. Use `z-index` values below the existing header (`1000`) except the card (`900`). Add:

```css
@keyframes reclamation-region-pulse {
  0%, 100% { fill-opacity: 0.42; filter: drop-shadow(0 0 2px rgba(249, 115, 22, 0.45)); }
  50% { fill-opacity: 0.82; filter: drop-shadow(0 0 8px rgba(249, 115, 22, 0.85)); }
}

.reclamation-region-pulse {
  animation: reclamation-region-pulse 1.6s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .reclamation-region-pulse { animation: none; }
}
```

At `max-width: 640px`, keep the map at least 480 px tall, stack scenario buttons only if needed, limit the card to `calc(100% - 16px)`, and move the legend above the bottom map attribution so controls do not overlap.

- [ ] **Step 5: Run focused frontend tests and verify GREEN**

```powershell
npm --prefix frontend run test -- src/test/ReclamationPage.test.tsx src/test/ReclamationMap.test.tsx src/test/ReclamationCanvasLayer.test.tsx src/test/reclamationCanvas.test.ts src/test/api.test.ts src/test/App.test.tsx
```

Expected: all selected tests pass with no unhandled promise rejections or React `act()` warnings.

- [ ] **Step 6: Run full automated verification**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/ -v -p no:cacheprovider
npm --prefix frontend run test
npm --prefix frontend run lint
npm run build
git diff --check
```

Expected: every command exits `0`. If unrelated pre-existing tests fail, record exact failing test names and prove all reclamation-focused tests pass; do not hide or rewrite unrelated user changes.

- [ ] **Step 7: Run real-data and browser acceptance**

Start FastAPI and Vite on explicit IPv4 hosts, then open `http://127.0.0.1:5173/reclamation` in the in-app browser. Verify:

1. China outline plus four orange demo polygons appear before any points request.
2. Pulse runs normally and is disabled when reduced-motion emulation is enabled.
3. Each region click requests only its region ID and displays exactly 2,471 / 8,702 / 4,392 / 3,735 points.
4. Current green is default; future blue switches without another points request.
5. Hollow points never open a card; filled points highlight on hover and open the four-metric card.
6. Card values use two decimals plus `千美元`; coordinates use six decimals. The legend exposes the four required value classes.
7. Back-to-China clears points/card and reselecting a cached region issues no request.
8. Desktop and 640 px viewport controls do not overlap; map pan/zoom, hover, and scenario switch remain responsive in the 8,702-point region.
9. Browser console has no application errors and the map contains two Canvas elements inside one `data-reclamation-canvas-layer` wrapper, not thousands of SVG paths.

Capture one nationwide screenshot and one selected-region screenshot for review without adding them to Git.

- [ ] **Step 8: Commit Task 8**

```powershell
git add frontend/src/components/ScenarioSwitch.tsx frontend/src/components/ReclamationLegend.tsx frontend/src/components/ReclamationInfoCard.tsx frontend/src/pages/ReclamationPage.tsx frontend/src/test/ReclamationPage.test.tsx frontend/src/App.tsx frontend/src/test/App.test.tsx frontend/src/App.css
git commit -m "feat: add reclamation potential assessment page"
```

## Final Review Gate

- Re-read `docs/superpowers/specs/2026-07-26-reclamation-potential-assessment-design.md` and map every completion criterion to test or browser evidence above.
- Confirm `git status --short` contains no unintended staged files and preserves unrelated user modifications.
- Confirm the final commit series contains only the eight task scopes and generated `data/reclamation` artifacts.
- Use `superpowers:verification-before-completion` before reporting completion.
