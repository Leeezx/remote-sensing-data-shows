# Dynamic Legend Thresholds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate six SSM legend thresholds from each selected raster's 2nd–98th percentile range and use the identical thresholds for the legend UI and tile rendering.

**Architecture:** Add a focused backend service that computes and caches an immutable legend from a COG path, modification time, base palette, and unit. The SSM legend endpoint and tile renderer call that service; the React app fetches the time-specific legend and keys its state by layer/time so stale responses can never be displayed.

**Tech Stack:** Python 3, FastAPI, rasterio, NumPy, pytest; React 19, TypeScript, Axios, Vitest, Testing Library.

---

## File map

- Create `backend/ssm_legend.py`: pure percentile-to-stops calculation, COG read, bounded cache, and public dynamic-legend API.
- Create `backend/tests/test_ssm_legend.py`: calculation, invalid-pixel, fallback, cache-hit, and cache-invalidation tests.
- Modify `backend/routers/layers.py`: expose `GET /api/layers/ssm/legend?time=...`.
- Modify `backend/routers/tiles.py`: obtain the same dynamic legend before coloring a tile.
- Modify `backend/tests/test_layers.py`: endpoint contract and error behavior.
- Modify `backend/tests/test_tiles.py`: prove tile coloring receives the shared dynamic legend.
- Modify `frontend/src/types/index.ts`: type the time-specific legend response and legend loading state.
- Modify `frontend/src/services/api.ts`: fetch a time-specific legend.
- Modify `frontend/src/components/Legend.tsx`: render explicit items plus loading/error states.
- Create `frontend/src/test/Legend.test.tsx`: presentational legend states.
- Modify `frontend/src/test/api.test.ts`: API request contract.
- Modify `frontend/src/App.tsx`: load and key dynamic legend state by selected SSM time.
- Modify `frontend/src/test/App.test.tsx`: successful loading, time changes, stale response protection, and errors.
- Modify `frontend/src/App.css`: style legend status text.

### Task 1: Dynamic SSM legend service

**Files:**
- Create: `backend/ssm_legend.py`
- Create: `backend/tests/test_ssm_legend.py`

- [ ] **Step 1: Write failing calculation and fallback tests**

Create `backend/tests/test_ssm_legend.py` with tests using a six-color `BASE_LEGEND`. Assert that `build_dynamic_legend`:

```python
import numpy as np

from backend import ssm_legend


BASE_LEGEND = [
    {"value": 0.09, "color": "#d53e4f", "label": "dry"},
    {"value": 0.15, "color": "#fc8d59", "label": "low"},
    {"value": 0.22, "color": "#fee08b", "label": "moderate"},
    {"value": 0.28, "color": "#99d594", "label": "moist"},
    {"value": 0.35, "color": "#3288bd", "label": "wet"},
    {"value": 0.40, "color": "#016c59", "label": "saturated"},
]


def test_build_dynamic_legend_uses_percentiles_and_preserves_colors():
    values = np.arange(101, dtype=np.float64).reshape(1, 101)
    result = ssm_legend.build_dynamic_legend(
        values, BASE_LEGEND, "m³/m³", source_mask=np.ones_like(values)
    )

    np.testing.assert_allclose(
        [item["value"] for item in result], np.linspace(2.0, 98.0, 6)
    )
    assert [item["color"] for item in result] == [
        item["color"] for item in BASE_LEGEND
    ]
    assert result[0]["label"] == "2.000 m³/m³"


def test_build_dynamic_legend_excludes_invalid_pixels():
    values = np.array([[0.1, 0.2, np.nan, np.inf, -999.0, -32768.0, 9.0]])
    source_mask = np.array([[1, 1, 1, 1, 1, 1, 0]], dtype=np.uint8)

    result = ssm_legend.build_dynamic_legend(
        values, BASE_LEGEND, "m³/m³", source_mask, nodata=-32768.0
    )

    assert result[0]["value"] == pytest.approx(0.102)
    assert result[-1]["value"] == pytest.approx(0.198)


@pytest.mark.parametrize(
    "values,source_mask",
    [
        (np.array([[np.nan, -999.0]]), np.ones((1, 2))),
        (np.array([[0.2, 0.2]]), np.ones((1, 2))),
    ],
)
def test_build_dynamic_legend_falls_back_without_a_usable_range(values, source_mask):
    assert ssm_legend.build_dynamic_legend(
        values, BASE_LEGEND, "m³/m³", source_mask
    ) == BASE_LEGEND
```

Include `import pytest`. Add one more assertion that a base legend with fewer than six entries is returned unchanged.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest backend/tests/test_ssm_legend.py -v`

Expected: collection fails with `ImportError: cannot import name 'ssm_legend' from 'backend'`.

- [ ] **Step 3: Implement the pure legend calculation**

Create `backend/ssm_legend.py` with:

```python
"""Time-specific SSM legend calculation and bounded caching."""

from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio

from backend.raster_rendering import valid_data_mask


LEGEND_STOP_COUNT = 6


def _copy_legend(legend):
    return [dict(item) for item in legend]


def build_dynamic_legend(
    values, base_legend, unit, source_mask=None, nodata=None
):
    base_legend = _copy_legend(base_legend)
    if len(base_legend) != LEGEND_STOP_COUNT:
        return base_legend

    values = np.asarray(values)
    valid = valid_data_mask(values, source_mask=source_mask, nodata=nodata)
    valid_values = values[valid]
    if valid_values.size == 0:
        return base_legend

    low, high = np.percentile(valid_values, [2, 98])
    if not np.isfinite(low) or not np.isfinite(high) or low >= high:
        return base_legend

    thresholds = np.linspace(float(low), float(high), LEGEND_STOP_COUNT)
    return [
        {
            "value": float(value),
            "color": base_legend[index]["color"],
            "label": f"{value:.3f} {unit}".strip(),
        }
        for index, value in enumerate(thresholds)
    ]
```

- [ ] **Step 4: Run calculation tests and verify GREEN**

Run: `python -m pytest backend/tests/test_ssm_legend.py -v`

Expected: all calculation/fallback tests pass.

- [ ] **Step 5: Write failing cache tests**

Add tests that monkeypatch `_read_dynamic_legend`, clear `_cached_dynamic_legend.cache_clear()`, call `get_dynamic_legend` twice, and assert one read. Then update the file modification timestamp with `cog_path.touch()` after a short explicit `os.utime` nanosecond change and assert a second read. Call with a changed base color and assert another read.

Use a fake result tuple such as:

```python
def fake_read(path, signature, unit):
    calls.append((path, signature, unit))
    return tuple((item[0], item[1], f"{item[0]:.3f} {unit}") for item in signature)
```

Expected public result remains a fresh list of dictionaries on every call.

- [ ] **Step 6: Run cache tests and verify RED**

Run: `python -m pytest backend/tests/test_ssm_legend.py -v`

Expected: FAIL because `get_dynamic_legend`, `_read_dynamic_legend`, and `_cached_dynamic_legend` do not exist.

- [ ] **Step 7: Implement COG reading and bounded caching**

Add these responsibilities to `backend/ssm_legend.py`:

```python
def _signature(base_legend):
    return tuple(
        (float(item["value"]), item["color"], item.get("label", ""))
        for item in base_legend
    )


def _read_dynamic_legend(path, signature, unit):
    base = [
        {"value": value, "color": color, "label": label}
        for value, color, label in signature
    ]
    with rasterio.open(path) as dataset:
        values = dataset.read(1)
        mask = dataset.read_masks(1)
        legend = build_dynamic_legend(
            values, base, unit, source_mask=mask, nodata=dataset.nodata
        )
    return tuple(
        (float(item["value"]), item["color"], item["label"])
        for item in legend
    )


@lru_cache(maxsize=64)
def _cached_dynamic_legend(path, modified_ns, signature, unit):
    del modified_ns
    return _read_dynamic_legend(path, signature, unit)


def get_dynamic_legend(cog_path: Path, base_legend, unit):
    path = cog_path.resolve()
    cached = _cached_dynamic_legend(
        str(path), path.stat().st_mtime_ns, _signature(base_legend), unit
    )
    return [
        {"value": value, "color": color, "label": label}
        for value, color, label in cached
    ]
```

- [ ] **Step 8: Run service tests and commit**

Run: `python -m pytest backend/tests/test_ssm_legend.py backend/tests/test_raster_rendering.py -v`

Expected: PASS.

Commit:

```bash
git add backend/ssm_legend.py backend/tests/test_ssm_legend.py
git commit -m "feat: compute cached SSM legend thresholds"
```

### Task 2: Shared backend endpoint and tile palette

**Files:**
- Modify: `backend/routers/layers.py`
- Modify: `backend/routers/tiles.py`
- Modify: `backend/tests/test_layers.py`
- Modify: `backend/tests/test_tiles.py`

- [ ] **Step 1: Write failing legend endpoint tests**

In `backend/tests/test_layers.py`, import `Path` and `backend.routers.layers as layers_router`. Add tests that monkeypatch `PROJECT_ROOT`, create `data/rasters/ssm/2010_01_cog.tif`, and monkeypatch `get_dynamic_legend` to return a known six-item list. Assert:

```python
response = client.get("/api/layers/ssm/legend", params={"time": "2010_01"})
assert response.status_code == 200
assert response.json() == {
    "layerId": "ssm",
    "time": "2010_01",
    "unit": "m³/m³",
    "legend": expected_legend,
}
```

Add cases for invalid time (422, `Invalid SSM time`) and missing file (404 with the expected COG name).

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `python -m pytest backend/tests/test_layers.py -v`

Expected: FAIL with 404 for `/api/layers/ssm/legend`.

- [ ] **Step 3: Implement the endpoint**

In `backend/routers/layers.py`, import `Path`, `Query`, `get_dynamic_legend`, and `ssm_time_to_cog_path`; define `PROJECT_ROOT` as in the tile router. Add the route before the generic layer-time route:

```python
@router.get("/layers/ssm/legend")
def ssm_legend(time: str = Query(...)):
    layer = get_layer("ssm")
    if layer is None:
        raise HTTPException(status_code=404, detail="SSM layer metadata is missing")
    try:
        cog_path = ssm_time_to_cog_path(
            PROJECT_ROOT / "data" / "rasters" / "ssm", time
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not cog_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"COG file not found for time '{time}' (looked for: {cog_path.name})",
        )
    legend = get_dynamic_legend(cog_path, layer["legend"], layer["unit"])
    return {"layerId": "ssm", "time": time, "unit": layer["unit"], "legend": legend}
```

- [ ] **Step 4: Run endpoint tests and verify GREEN**

Run: `python -m pytest backend/tests/test_layers.py -v`

Expected: PASS.

- [ ] **Step 5: Write a failing tile-sharing test**

Update `test_render_ssm_tile_reads_first_band_and_mask_from_cog` in `backend/tests/test_tiles.py` to monkeypatch `tiles.get_dynamic_legend`, record its COG path/base legend/unit arguments, and return a two-stop known legend. Assert `_render_ssm_tile` passed that returned legend to coloring by checking decoded endpoint colors. Keep the existing first-band and source-mask assertions.

- [ ] **Step 6: Run the focused tile test and verify RED**

Run: `python -m pytest backend/tests/test_tiles.py::test_render_ssm_tile_reads_first_band_and_mask_from_cog -v`

Expected: FAIL because `_render_ssm_tile` still passes the fixed metadata legend directly to `colorize`.

- [ ] **Step 7: Make tile rendering consume the shared legend**

Import `get_dynamic_legend` in `backend/routers/tiles.py` and change `_render_ssm_tile` before opening the tile:

```python
legend = get_dynamic_legend(cog_path, legend, layer.get("unit", ""))
```

Keep `source_mask=image.mask` unchanged so transparency behavior is unaffected.

- [ ] **Step 8: Run backend regression tests and commit**

Run: `python -m pytest backend/tests/test_layers.py backend/tests/test_tiles.py backend/tests/test_ssm_legend.py -v`

Expected: PASS.

Commit:

```bash
git add backend/routers/layers.py backend/routers/tiles.py backend/tests/test_layers.py backend/tests/test_tiles.py
git commit -m "feat: share dynamic legend with SSM tiles"
```

### Task 3: Frontend legend contract and presentation

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/Legend.tsx`
- Modify: `frontend/src/App.css`
- Create: `frontend/src/test/Legend.test.tsx`
- Modify: `frontend/src/test/api.test.ts`

- [ ] **Step 1: Write failing API and component tests**

Mock Axios in `frontend/src/test/api.test.ts` using `vi.mock('axios', ...)` following the module's `axios.create` shape. Assert `getLayerLegend('ssm', '2010_01')` calls:

```typescript
expect(clientGet).toHaveBeenCalledWith('/layers/ssm/legend', {
  params: { time: '2010_01' },
})
```

Create `frontend/src/test/Legend.test.tsx` with a layer containing static labels and assert:

```tsx
render(<Legend layer={layer} items={dynamicItems} status="ready" />)
expect(screen.getByText('0.123 m³/m³')).toBeInTheDocument()
expect(screen.queryByText('static label')).not.toBeInTheDocument()
```

Also assert `status="loading"` renders `正在加载图例...` without items, and `status="error"` renders `图例暂不可用` without items.

- [ ] **Step 2: Run frontend focused tests and verify RED**

Run: `cd frontend; npx vitest run src/test/api.test.ts src/test/Legend.test.tsx`

Expected: FAIL because the response type, API function, and new Legend props do not exist.

- [ ] **Step 3: Add types and API function**

In `frontend/src/types/index.ts` add:

```typescript
export interface LayerLegendResponse {
  layerId: string
  time: string
  unit: string
  legend: LegendItem[]
}

export type LegendStatus = 'ready' | 'loading' | 'error'
```

Import `LayerLegendResponse` in `frontend/src/services/api.ts` and add:

```typescript
export async function getLayerLegend(
  layerId: string,
  time: string,
): Promise<LayerLegendResponse> {
  const { data } = await client.get(`/layers/${layerId}/legend`, {
    params: { time },
  })
  return data
}
```

- [ ] **Step 4: Update the presentational Legend component**

Change `Legend` props to `layer`, `items`, and `status`. Default `items` to `layer?.legend ?? []` and `status` to `ready`. Render the heading whenever a layer exists; render exactly one status message for loading/error, otherwise map `items`. Use `item.value` plus `item.color` as the key instead of the array index.

Add `.legend-status { color: #666; white-space: nowrap; }` to `frontend/src/App.css`.

- [ ] **Step 5: Run focused frontend tests and commit**

Run: `cd frontend; npx vitest run src/test/api.test.ts src/test/Legend.test.tsx`

Expected: PASS.

Commit:

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts frontend/src/components/Legend.tsx frontend/src/App.css frontend/src/test/Legend.test.tsx frontend/src/test/api.test.ts
git commit -m "feat: support time-specific legend display"
```

### Task 4: Time-keyed dynamic legend loading

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/test/App.test.tsx`

- [ ] **Step 1: Write failing integration and race tests**

Extend the hoisted API mocks with `getLayerLegend`. In `beforeEach`, resolve an initial response for `2025-01-01` containing label `0.123 m³/m³`.

Add a success test that waits for that label and asserts:

```typescript
expect(apiMocks.getLayerLegend).toHaveBeenCalledWith('ssm', '2025-01-01')
```

Add a race test with two deferred promises. Resolve the initial request, click the button titled `下一个`, leave the second request pending, and assert the initial label disappears while `正在加载图例...` is visible. Resolve the second request with `0.234 m³/m³`, then resolve an older deferred request afterward; assert only `0.234 m³/m³` remains.

Add a rejection test asserting `图例暂不可用` and no static legend item.

- [ ] **Step 2: Run App tests and verify RED**

Run: `cd frontend; npx vitest run src/test/App.test.tsx`

Expected: FAIL because `App` never calls `getLayerLegend` and still passes only the layer to `Legend`.

- [ ] **Step 3: Implement keyed legend state**

In `frontend/src/App.tsx`, import `getLayerLegend`, `LegendItem`, and `LegendStatus`. Add state shaped as:

```typescript
interface DynamicLegendState {
  key: string
  status: LegendStatus
  items: LegendItem[]
}

const [dynamicLegend, setDynamicLegend] = useState<DynamicLegendState>({
  key: '', status: 'loading', items: [],
})
```

Derive `activeLayer` and `legendKey = activeLayerId === 'ssm' && currentTime ? `${activeLayerId}:${currentTime}` : ''`.

Add an effect depending on `activeLayerId`, `currentTime`, and `legendKey`. For non-SSM layers return without requesting. For SSM with an empty time, clear to loading. Otherwise set `{key: legendKey, status: 'loading', items: []}`, call `getLayerLegend`, and use a local `cancelled` flag in cleanup. On success set ready items for the same key; on failure set error for the same key.

At render time, do not trust state whose key differs from `legendKey`:

```typescript
const ssmLegendStatus: LegendStatus =
  dynamicLegend.key === legendKey ? dynamicLegend.status : 'loading'
const legendItems = activeLayer?.id === 'ssm'
  ? (dynamicLegend.key === legendKey ? dynamicLegend.items : [])
  : (activeLayer?.legend ?? [])
```

Pass `activeLayer`, `legendItems`, and the appropriate status to `Legend`.

- [ ] **Step 4: Run App and full frontend tests**

Run: `cd frontend; npx vitest run src/test/App.test.tsx`

Expected: PASS.

Run: `npm run test:frontend`

Expected: all frontend tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/test/App.test.tsx
git commit -m "feat: load dynamic legend for selected SSM time"
```

### Task 5: Full verification and browser acceptance

**Files:**
- No production changes expected.
- Update tests only if verification exposes a requirement gap; do not weaken assertions.

- [ ] **Step 1: Run complete automated verification**

Run:

```powershell
npm run test:backend
npm run test:frontend
cd frontend; npm run lint
cd frontend; npm run build
```

Expected: every command exits 0. Existing documented non-blocking lint warnings may remain, but no new warning may be introduced.

- [ ] **Step 2: Verify data and diff hygiene**

Run: `python data/validate_data.py`

Expected: validation passes.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 3: Browser acceptance**

Start the existing backend and frontend development servers. In the browser:

1. Open the default SSM layer and note all six threshold labels.
2. Confirm the map uses multiple colors and the legend values lie within that time's displayed data distribution.
3. Switch to a different 8-day time and confirm both labels and map colors update together.
4. Zoom and pan; confirm thresholds do not change.
5. Switch times rapidly; confirm no old labels flash after the final selection.
6. Confirm point and area query values remain raw values and NoData remains transparent.

- [ ] **Step 4: Final commit only if verification required fixes**

Stage only files changed for this feature and commit with a narrowly scoped message. Do not include existing untracked planning files or images.

