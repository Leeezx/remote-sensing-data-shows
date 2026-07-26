# Map Rendering and Query Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make raster colors match the legend, render every NoData form transparently, and replace region/chart/right-panel UI with automatic map query cards.

**Architecture:** Layer metadata becomes the single source for numeric color stops. A small backend raster-rendering module masks invalid values and converts numeric tiles to RGBA, while `MapView` owns query geometry and a tested query-state hook drives a fixed map card. The backend region and series routes remain intact; only unused frontend consumers are removed.

**Tech Stack:** Python 3, FastAPI, NumPy, rasterio, rio-tiler, pytest, React 19, TypeScript, Leaflet/react-leaflet, Axios, Vitest, Testing Library.

---

## File map

- Create `backend/raster_rendering.py`: shared valid-data mask, legend interpolation, and PNG encoding.
- Create `backend/tests/test_raster_rendering.py`: exact palette and transparency regression tests.
- Modify `backend/routers/tiles.py`: render SSM COG tiles locally with the shared metadata palette.
- Modify `backend/routers/query.py`: apply the shared NoData mask to point and area queries.
- Modify `backend/tests/test_tiles.py` and `backend/tests/test_query.py`: endpoint and NoData regressions.
- Modify `data/metadata/layers.json`, `data/validate_data.py`, and `data/schema.md`: make numeric legend stops explicit and validated.
- Modify `frontend/src/types/index.ts`: add `LegendItem.value` and map-query state types.
- Create `frontend/src/components/QueryCard.tsx` and `frontend/src/test/QueryCard.test.tsx`: present query states independently from Leaflet.
- Create `frontend/src/hooks/useMapQuery.ts` and `frontend/src/test/useMapQuery.test.tsx`: own asynchronous point/area requests and stale-response protection.
- Modify `frontend/src/components/MapView.tsx`: own marker/rectangle state and invoke automatic queries.
- Modify `frontend/src/App.tsx`, `frontend/src/components/Sidebar.tsx`, `frontend/src/components/ExportPanel.tsx`, and `frontend/src/App.css`: remove region/chart/right-panel plumbing.
- Delete `frontend/src/components/QueryPanel.tsx` and `frontend/src/components/ChartPanel.tsx`.
- Modify `frontend/src/services/api.ts`, `frontend/src/test/App.test.tsx`, `frontend/package.json`, and `frontend/package-lock.json`: remove unused APIs/dependencies and add a test script.

Preserve the existing uncommitted `useMemo` change in `MapView.tsx` and flex rules in `App.css`; inspect each staged diff before any commit.

### Task 1: Make numeric legend stops and raster colorization testable

**Files:**
- Create: `backend/tests/test_raster_rendering.py`
- Create: `backend/raster_rendering.py`
- Modify: `backend/tests/test_layers.py`
- Modify: `data/metadata/layers.json`
- Modify: `data/validate_data.py`
- Modify: `data/schema.md`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Write failing palette and metadata tests**

Create `backend/tests/test_raster_rendering.py`:

```python
import numpy as np

from backend.raster_rendering import colorize, valid_data_mask


LEGEND = [
    {"value": 0.09, "color": "#d53e4f", "label": "dry"},
    {"value": 0.15, "color": "#fc8d59", "label": "low"},
    {"value": 0.22, "color": "#fee08b", "label": "moderate"},
    {"value": 0.28, "color": "#99d594", "label": "moist"},
    {"value": 0.35, "color": "#3288bd", "label": "wet"},
    {"value": 0.40, "color": "#016c59", "label": "saturated"},
]


def test_colorize_matches_every_legend_stop():
    values = np.array([[item["value"] for item in LEGEND]], dtype=np.float32)
    rgba = colorize(values, LEGEND)
    assert rgba[0].tolist() == [
        [213, 62, 79, 255],
        [252, 141, 89, 255],
        [254, 224, 139, 255],
        [153, 213, 148, 255],
        [50, 136, 189, 255],
        [1, 108, 89, 255],
    ]


def test_colorize_interpolates_and_clamps_valid_values():
    values = np.array([[0.01, 0.12, 0.50]], dtype=np.float32)
    rgba = colorize(values, LEGEND)
    assert rgba[0, 0].tolist() == [213, 62, 79, 255]
    assert rgba[0, 1].tolist() == [232, 102, 84, 255]
    assert rgba[0, 2].tolist() == [1, 108, 89, 255]


def test_valid_data_mask_rejects_nan_minus_999_source_mask_and_declared_nodata():
    values = np.array([[0.2, np.nan, -999.0, -32768.0, 0.3]], dtype=np.float32)
    source_mask = np.array([[255, 255, 255, 255, 0]], dtype=np.uint8)
    mask = valid_data_mask(values, source_mask=source_mask, nodata=-32768.0)
    assert mask.tolist() == [[True, False, False, False, False]]


def test_colorize_makes_all_invalid_values_transparent():
    values = np.array([[np.nan, -999.0, 0.2]], dtype=np.float32)
    rgba = colorize(values, LEGEND)
    assert rgba[0, :, 3].tolist() == [0, 0, 255]
```

Extend `test_layer_fields` in `backend/tests/test_layers.py`:

```python
for layer in data:
    for item in layer["legend"]:
        assert isinstance(item["value"], (int, float))
        assert isinstance(item["color"], str)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_raster_rendering.py backend/tests/test_layers.py -q
```

Expected: collection fails because `backend.raster_rendering` does not exist; after creating only the empty module, metadata assertions fail because `value` is missing.

- [ ] **Step 3: Implement the minimal shared raster functions**

Create `backend/raster_rendering.py`:

```python
"""Shared raster masking and metadata-driven colorization."""

import numpy as np
from rio_tiler.utils import render

FALLBACK_NODATA = -999.0


def _hex_rgb(value: str) -> tuple[int, int, int]:
    text = value.removeprefix("#")
    if len(text) != 6:
        raise ValueError(f"Expected #rrggbb color, got {value!r}")
    return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))


def valid_data_mask(
    values: np.ndarray,
    source_mask: np.ndarray | None = None,
    nodata: float | None = None,
) -> np.ndarray:
    valid = np.isfinite(values) & (values != FALLBACK_NODATA)
    if nodata is not None and np.isfinite(nodata):
        valid &= values != nodata
    if source_mask is not None:
        valid &= source_mask.astype(bool)
    return valid


def colorize(
    values: np.ndarray,
    legend: list[dict],
    source_mask: np.ndarray | None = None,
    nodata: float | None = None,
) -> np.ndarray:
    if values.ndim != 2:
        raise ValueError("colorize expects a two-dimensional raster band")
    stops = sorted(legend, key=lambda item: item["value"])
    stop_values = np.array([item["value"] for item in stops], dtype=np.float64)
    stop_colors = np.array([_hex_rgb(item["color"]) for item in stops], dtype=np.float64)
    valid = valid_data_mask(values, source_mask=source_mask, nodata=nodata)
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    safe_values = np.nan_to_num(values, nan=stop_values[0])
    for channel in range(3):
        interpolated = np.interp(safe_values, stop_values, stop_colors[:, channel])
        rgba[..., channel] = np.rint(interpolated).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return rgba


def render_png(rgba: np.ndarray) -> bytes:
    return render(np.moveaxis(rgba, -1, 0), img_format="PNG")
```

- [ ] **Step 4: Add numeric values to metadata and validation**

For every legend entry in `data/metadata/layers.json`, add a numeric `value` matching the number currently embedded in its label. Update `data/validate_data.py` inside the legend loop:

```python
if "value" not in stop or not isinstance(stop["value"], (int, float)):
    errors.append(f"{prefix}: legend[{j}].value must be numeric")
```

Update the legend schema example in `data/schema.md` to `{ "value": number, "color": "#hex", "label": string }`. Update `LegendItem` in `frontend/src/types/index.ts`:

```typescript
export interface LegendItem {
  value: number
  color: string
  label: string
}
```

- [ ] **Step 5: Run tests and data validation for GREEN**

Run:

```powershell
python -m pytest backend/tests/test_raster_rendering.py backend/tests/test_layers.py -q
python data/validate_data.py
```

Expected: all selected tests pass and validation reports no errors.

- [ ] **Step 6: Review and commit only Task 1 files**

```powershell
git diff --check
git add backend/raster_rendering.py backend/tests/test_raster_rendering.py backend/tests/test_layers.py data/metadata/layers.json data/validate_data.py data/schema.md frontend/src/types/index.ts
git diff --cached --stat
git commit -m "feat: drive raster colors from legend metadata"
```

### Task 2: Replace the SSM self-proxy renderer with transparent RGBA tiles

**Files:**
- Modify: `backend/routers/tiles.py`
- Modify: `backend/tests/test_tiles.py`

- [ ] **Step 1: Write failing endpoint and local-render tests**

Add to `backend/tests/test_tiles.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

import backend.routers.tiles as tiles


def test_render_ssm_tile_uses_image_mask_and_metadata_palette(monkeypatch, tmp_path):
    image = MagicMock()
    image.data = np.array([[[0.09, -999.0]]], dtype=np.float32)
    image.mask = np.array([[255, 255]], dtype=np.uint8)
    reader = MagicMock()
    reader.__enter__.return_value.tile.return_value = image
    reader.__exit__.return_value = False
    monkeypatch.setattr(tiles, "COGReader", lambda _: reader)
    png = tiles._render_ssm_tile(tmp_path / "sample.tif", 1, 2, 3)
    assert png.startswith(b"\x89PNG")
    reader.__enter__.return_value.tile.assert_called_once_with(1, 2, 3)


def test_ssm_tile_endpoint_does_not_accept_frontend_colormap(monkeypatch, tmp_path):
    raster_dir = tmp_path / "data" / "rasters" / "ssm"
    raster_dir.mkdir(parents=True)
    (raster_dir / "2010_01_cog.tif").touch()
    monkeypatch.setattr(tiles, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tiles, "_render_ssm_tile", lambda *args: tiles.TRANSPARENT_PNG)
    response = client.get("/data/ssm-tiles/WebMercatorQuad/4/12/6.png?time=2010_01")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
```

- [ ] **Step 2: Run the focused tile tests and verify RED**

Run:

```powershell
python -m pytest backend/tests/test_tiles.py -q
```

Expected: FAIL because `_render_ssm_tile` and `COGReader` are not defined in `tiles.py`.

- [ ] **Step 3: Implement local metadata-driven rendering**

Replace the `httpx` self-request in `backend/routers/tiles.py` with:

```python
from fastapi.responses import FileResponse, Response
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import COGReader

from backend.data_loader import get_layer
from backend.raster_rendering import colorize, render_png


def _render_ssm_tile(cog_path: Path, x: int, y: int, z: int) -> bytes:
    layer = get_layer("ssm")
    if layer is None:
        raise RuntimeError("SSM layer metadata is missing")
    with COGReader(str(cog_path)) as reader:
        image = reader.tile(x, y, z)
    rgba = colorize(image.data[0], layer["legend"], source_mask=image.mask)
    return render_png(rgba)
```

Keep the existing route path and `tileMatrixSetId` parameter for URL compatibility, but remove `colormap_name` and `rescale` query parameters. Return `Response(content=png, media_type="image/png")`. Catch `TileOutsideBounds` and return `TRANSPARENT_PNG`; keep missing COG files as a descriptive 404.

- [ ] **Step 4: Run tile tests for GREEN**

```powershell
python -m pytest backend/tests/test_tiles.py backend/tests/test_raster_rendering.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Review and commit Task 2**

```powershell
git add backend/routers/tiles.py backend/tests/test_tiles.py
git diff --cached --check
git commit -m "fix: render SSM tiles with shared palette and alpha"
```

### Task 3: Apply the same NoData rules to point and area queries

**Files:**
- Modify: `backend/routers/query.py`
- Modify: `backend/tests/test_query.py`

- [ ] **Step 1: Write failing NoData query tests**

Add these imports, fake raster, and tests to `backend/tests/test_query.py`:

```python
class FakeRaster:
    crs = "EPSG:4326"
    width = 2
    height = 2

    def __init__(self, values, nodata=None):
        self.values = np.asarray(values, dtype=np.float32)
        self.nodata = nodata

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def index(self, x, y):
        return (0, 0)

    def read(self, band, window):
        return self.values


@pytest.mark.parametrize("value", [np.nan, -999.0])
def test_ssm_point_query_rejects_every_nodata_form(monkeypatch, tmp_path, value):
    cog_path = tmp_path / "sample.tif"
    cog_path.touch()
    monkeypatch.setattr(query, "_ssm_time_to_cog_path", lambda _: cog_path)
    monkeypatch.setattr(query.rasterio, "open", lambda _: FakeRaster([[value]]))
    layer = {"id": "ssm", "unit": "m³/m³"}
    with pytest.raises(HTTPException) as error:
        query._query_point_SSM(layer, "2010-01-01", 104.0, 36.0)
    assert error.value.status_code == 404


def test_ssm_area_query_excludes_nan_and_minus_999(monkeypatch, tmp_path):
    cog_path = tmp_path / "sample.tif"
    cog_path.touch()
    values = [[0.2, -999.0], [np.nan, 0.4]]
    monkeypatch.setattr(query, "_ssm_time_to_cog_path", lambda _: cog_path)
    monkeypatch.setattr(query.rasterio, "open", lambda _: FakeRaster(values))
    result = query._query_area_SSM({"id": "ssm"}, "2010-01-01", 100, 30, 101, 31)
    assert result == pytest.approx({"mean": 0.3, "max": 0.4, "min": 0.2, "count": 2})


def test_ssm_area_query_rejects_an_all_nodata_area(monkeypatch, tmp_path):
    cog_path = tmp_path / "sample.tif"
    cog_path.touch()
    monkeypatch.setattr(query, "_ssm_time_to_cog_path", lambda _: cog_path)
    monkeypatch.setattr(query.rasterio, "open", lambda _: FakeRaster([[np.nan, -999.0]]))
    with pytest.raises(HTTPException) as error:
        query._query_area_SSM({"id": "ssm"}, "2010-01-01", 100, 30, 101, 31)
    assert error.value.status_code == 404
```

The file needs `import numpy as np`, `import pytest`, `from fastapi import HTTPException`, and `import backend.routers.query as query`.

- [ ] **Step 2: Run focused query tests and verify RED**

```powershell
python -m pytest backend/tests/test_query.py -q
```

Expected: the `-999` point case returns a normal value and fails; area assertions expose any unfiltered fallback NoData.

- [ ] **Step 3: Reuse `valid_data_mask` in query helpers**

In `backend/routers/query.py`, import `valid_data_mask`. Replace point validation with:

```python
if not valid_data_mask(np.array([[value]]), nodata=src.nodata)[0, 0]:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="No valid data at this point",
    )
```

Replace the area filtering with:

```python
mask = valid_data_mask(data, nodata=src.nodata)
valid = data[mask]
```

Keep the existing 404 response when `valid.size == 0`.

- [ ] **Step 4: Run focused and full backend tests**

```powershell
python -m pytest backend/tests/test_query.py -q
python -m pytest backend/tests -q
```

Expected: all backend tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add backend/routers/query.py backend/tests/test_query.py
git commit -m "fix: exclude all NoData forms from spatial queries"
```

### Task 4: Build a pure query-card component

**Files:**
- Create: `frontend/src/components/QueryCard.tsx`
- Create: `frontend/src/test/QueryCard.test.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/App.css`

- [ ] **Step 1: Define query-card state and failing component tests**

Add to `frontend/src/types/index.ts`:

```typescript
export type MapQueryState =
  | { status: 'idle' }
  | { status: 'loading'; kind: 'point' | 'area' }
  | { status: 'error'; kind: 'point' | 'area'; message: string }
  | { status: 'point'; result: PointQueryResult }
  | { status: 'area'; result: AreaQueryResult }
```

Create `frontend/src/test/QueryCard.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import QueryCard from '../components/QueryCard'

const layer = {
  id: 'ssm', name: '表层土壤水分', description: '', type: 'soil', unit: 'm³/m³',
  range: { min: 0, max: 0.5 }, timeRange: { start: '2010-01', end: '2013-12', step: '8day' },
  tileTemplate: '', legend: [],
}

describe('QueryCard', () => {
  it('shows area loading', () => {
    render(<QueryCard state={{ status: 'loading', kind: 'area' }} activeLayer={layer} onClose={() => {}} />)
    expect(screen.getByText('正在统计框选区域…')).toBeInTheDocument()
  })

  it('shows a point result', () => {
    render(<QueryCard state={{ status: 'point', result: {
      layerId: 'ssm', time: '2010-01-01', lng: 104, lat: 36, value: 0.284, unit: 'm³/m³',
    } }} activeLayer={layer} onClose={() => {}} />)
    expect(screen.getByText('点查询结果')).toBeInTheDocument()
    expect(screen.getByText(/0.2840/)).toBeInTheDocument()
  })

  it('shows every area statistic', () => {
    render(<QueryCard state={{ status: 'area', result: { mean: 0.2, max: 0.4, min: 0.1, count: 8 } }} activeLayer={layer} onClose={() => {}} />)
    for (const label of ['平均值', '最大值', '最小值', '像元数']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('shows errors and closes', async () => {
    const onClose = vi.fn()
    render(<QueryCard state={{ status: 'error', kind: 'point', message: '该位置无有效数据' }} activeLayer={layer} onClose={onClose} />)
    expect(screen.getByText('该位置无有效数据')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '关闭查询结果' }))
    expect(onClose).toHaveBeenCalledOnce()
  })
})
```

- [ ] **Step 2: Run QueryCard tests and verify RED**

```powershell
Set-Location frontend
npx vitest run src/test/QueryCard.test.tsx
```

Expected: FAIL because `QueryCard.tsx` does not exist.

- [ ] **Step 3: Implement `QueryCard`**

Create a component with this public contract:

```typescript
interface QueryCardProps {
  state: MapQueryState
  activeLayer: Layer | null
  onClose: () => void
}

export default function QueryCard({ state, activeLayer, onClose }: QueryCardProps) {
  if (state.status === 'idle') return null
  return (
    <section className="query-card" aria-live="polite">
      <button className="query-card-close" type="button" aria-label="关闭查询结果" onClick={onClose}>×</button>
      {state.status === 'loading' && <p>{state.kind === 'point' ? '正在查询点位…' : '正在统计框选区域…'}</p>}
      {state.status === 'error' && <p className="error">{state.message}</p>}
      {state.status === 'point' && (
        <div><h4>点查询结果</h4><dl>
          <dt>坐标</dt><dd>{state.result.lat}, {state.result.lng}</dd>
          <dt>图层</dt><dd>{activeLayer?.name ?? state.result.layerId}</dd>
          <dt>时间</dt><dd>{state.result.time}</dd>
          <dt>数值</dt><dd>{state.result.value.toFixed(4)} {state.result.unit}</dd>
        </dl></div>
      )}
      {state.status === 'area' && (
        <div><h4>框选区域统计</h4><dl>
          <dt>平均值</dt><dd>{state.result.mean.toFixed(4)}</dd>
          <dt>最大值</dt><dd>{state.result.max.toFixed(4)}</dd>
          <dt>最小值</dt><dd>{state.result.min.toFixed(4)}</dd>
          <dt>像元数</dt><dd>{state.result.count}</dd>
        </dl></div>
      )}
    </section>
  )
}
```

Add fixed top-right card styles under `.map-container` in `App.css`, with `z-index: 600`, `max-width: min(320px, calc(100% - 24px))`, white translucent background, close button, and two-column `dl` layout. Do not remove the pre-existing flex changes.

- [ ] **Step 4: Run QueryCard tests for GREEN**

```powershell
npx vitest run src/test/QueryCard.test.tsx
```

Expected: all QueryCard tests pass.

- [ ] **Step 5: Review Task 4 diff without overwriting existing CSS work**

```powershell
git diff -- frontend/src/App.css frontend/src/types/index.ts frontend/src/components/QueryCard.tsx frontend/src/test/QueryCard.test.tsx
```

Commit only after confirming the original `.map-area-wrapper` flex declarations remain present.

### Task 5: Add automatic, race-safe point and box query state

**Files:**
- Create: `frontend/src/hooks/useMapQuery.ts`
- Create: `frontend/src/test/useMapQuery.test.tsx`
- Modify: `frontend/src/components/MapView.tsx`

- [ ] **Step 1: Write failing hook tests**

Create `frontend/src/test/useMapQuery.test.tsx`:

```tsx
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { queryArea, queryPoint } from '../services/api'
import { useMapQuery } from '../hooks/useMapQuery'

vi.mock('../services/api', () => ({ queryPoint: vi.fn(), queryArea: vi.fn() }))

const point = { layerId: 'ssm', time: '2010-01-01', lng: 104, lat: 36, value: 0.2, unit: 'm³/m³' }

describe('useMapQuery', () => {
  beforeEach(() => vi.clearAllMocks())

  it('loads and stores a point result', async () => {
    vi.mocked(queryPoint).mockResolvedValue(point)
    const { result } = renderHook(() => useMapQuery('ssm', '2010-01-01'))
    await act(async () => { await result.current.queryPointAt(36, 104) })
    expect(queryPoint).toHaveBeenCalledWith('ssm', '2010-01-01', 104, 36)
    expect(result.current.state).toEqual({ status: 'point', result: point })
  })

  it('automatically posts a closed area polygon', async () => {
    vi.mocked(queryArea).mockResolvedValue({ mean: 0.2, max: 0.3, min: 0.1, count: 4 })
    const { result } = renderHook(() => useMapQuery('ssm', '2010-01-01'))
    await act(async () => { await result.current.queryAreaBounds([[30, 100], [31, 101]]) })
    expect(queryArea).toHaveBeenCalledWith({ layerId: 'ssm', time: '2010-01-01', geometry: {
      type: 'Polygon', coordinates: [[[100, 30], [101, 30], [101, 31], [100, 31], [100, 30]]],
    } })
    expect(result.current.state.status).toBe('area')
  })

  it('turns a point 404 into a no-data card', async () => {
    vi.mocked(queryPoint).mockRejectedValue({ response: { status: 404 } })
    const { result } = renderHook(() => useMapQuery('ssm', '2010-01-01'))
    await act(async () => { await result.current.queryPointAt(36, 104) })
    expect(result.current.state).toEqual({ status: 'error', kind: 'point', message: '该位置无有效数据' })
  })

  it('ignores a stale response after reset', async () => {
    let resolvePoint!: (value: typeof point) => void
    vi.mocked(queryPoint).mockReturnValue(new Promise((resolve) => { resolvePoint = resolve }))
    const { result } = renderHook(() => useMapQuery('ssm', '2010-01-01'))
    act(() => { void result.current.queryPointAt(36, 104) })
    expect(result.current.state).toEqual({ status: 'loading', kind: 'point' })
    act(() => result.current.reset())
    await act(async () => resolvePoint(point))
    expect(result.current.state).toEqual({ status: 'idle' })
  })
})
```

- [ ] **Step 2: Run hook tests and verify RED**

```powershell
npx vitest run src/test/useMapQuery.test.tsx
```

Expected: FAIL because the hook does not exist.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/hooks/useMapQuery.ts`:

```typescript
import { useCallback, useEffect, useRef, useState } from 'react'
import { queryArea, queryPoint } from '../services/api'
import type { MapQueryState } from '../types'

function errorMessage(error: unknown, kind: 'point' | 'area'): string {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 404) return kind === 'point' ? '该位置无有效数据' : '该区域无有效数据'
  return kind === 'point' ? '点查询失败，请重试' : '区域查询失败，请重试'
}

export function useMapQuery(activeLayerId: string | null, currentTime: string): {
  state: MapQueryState
  queryPointAt: (lat: number, lng: number) => Promise<void>
  queryAreaBounds: (coords: [number, number][]) => Promise<void>
  reset: () => void
} {
  const [state, setState] = useState<MapQueryState>({ status: 'idle' })
  const requestIdRef = useRef(0)

  const reset = useCallback(() => {
    requestIdRef.current += 1
    setState({ status: 'idle' })
  }, [])

  useEffect(() => reset(), [activeLayerId, currentTime, reset])

  const queryPointAt = useCallback(async (lat: number, lng: number) => {
    if (!activeLayerId || !currentTime) return
    const requestId = ++requestIdRef.current
    const roundedLat = Number(lat.toFixed(4))
    const roundedLng = Number(lng.toFixed(4))
    setState({ status: 'loading', kind: 'point' })
    try {
      const result = await queryPoint(activeLayerId, currentTime, roundedLng, roundedLat)
      if (requestId === requestIdRef.current) setState({ status: 'point', result })
    } catch (error) {
      if (requestId === requestIdRef.current) {
        setState({ status: 'error', kind: 'point', message: errorMessage(error, 'point') })
      }
    }
  }, [activeLayerId, currentTime])

  const queryAreaBounds = useCallback(async (coords: [number, number][]) => {
    if (!activeLayerId || !currentTime || coords.length !== 2) return
    const requestId = ++requestIdRef.current
    const [p1, p2] = coords
    setState({ status: 'loading', kind: 'area' })
    try {
      const result = await queryArea({
        layerId: activeLayerId,
        time: currentTime,
        geometry: { type: 'Polygon', coordinates: [[
          [p1[1], p1[0]], [p2[1], p1[0]], [p2[1], p2[0]],
          [p1[1], p2[0]], [p1[1], p1[0]],
        ]] },
      })
      if (requestId === requestIdRef.current) setState({ status: 'area', result })
    } catch (error) {
      if (requestId === requestIdRef.current) {
        setState({ status: 'error', kind: 'area', message: errorMessage(error, 'area') })
      }
    }
  }, [activeLayerId, currentTime])

  return { state, queryPointAt, queryAreaBounds, reset }
}
```

The request id prevents an older point or area response from overwriting state after a reset or a newer query.

- [ ] **Step 4: Connect MapEvents and MapView**

Change `MapEvents` to emit coordinates only; it must not call APIs directly. In `MapView`:

- keep the existing `useMemo` active-layer change;
- store `marker` and `rect` together with the hook state;
- on click, set marker, clear rectangle, and call `queryPointAt`;
- on Shift mouseup, set rectangle, clear marker, and call `queryAreaBounds` immediately;
- render `<QueryCard>` outside `MapContainer` but inside `.map-container` so CSS positioning is stable;
- render `<Marker>` directly from `marker` and remove the separate `PointMarker` event component;
- on card close, layer change, or time change, call `reset()` and clear marker/rectangle.

- [ ] **Step 5: Run hook tests and TypeScript build**

```powershell
npx vitest run src/test/useMapQuery.test.tsx src/test/QueryCard.test.tsx
npm run build
```

Expected: tests pass and TypeScript/Vite build exits 0.

- [ ] **Step 6: Review overlapping MapView changes before commit**

```powershell
git diff -- frontend/src/components/MapView.tsx
```

Confirm the user’s `useMemo` change is preserved. Stage the hook, tests, card, types, CSS, and MapView only after this review.

### Task 6: Remove region filtering, charts, and the right panel

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/components/ExportPanel.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/test/App.test.tsx`
- Modify: `frontend/src/App.css`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Delete: `frontend/src/components/QueryPanel.tsx`
- Delete: `frontend/src/components/ChartPanel.tsx`

- [ ] **Step 1: Expand the App test to describe the stripped layout**

Replace `frontend/src/test/App.test.tsx` with:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { getLayers, getLayerTimes } from '../services/api'
import App from '../App'

vi.mock('../services/api', () => ({
  getLayers: vi.fn().mockResolvedValue([{
    id: 'ssm', name: '表层土壤水分', description: '', type: 'soil', unit: 'm³/m³',
    range: { min: 0, max: 0.5 }, timeRange: { start: '2010-01', end: '2013-12', step: '8day' },
    tileTemplate: '', legend: [],
  }]),
  getLayerTimes: vi.fn().mockResolvedValue(['2010-01-01']),
  getRegions: vi.fn().mockResolvedValue([]),
  getSeries: vi.fn().mockResolvedValue([]),
  queryPoint: vi.fn(), queryArea: vi.fn(), login: vi.fn(),
  getExportCsvUrl: vi.fn().mockReturnValue('/api/export/csv'),
}))

vi.mock('../components/MapView', () => ({ default: () => <div data-testid="map-view" /> }))

describe('App', () => {
  it('renders the map without region filters, charts, or a right panel', async () => {
    render(<App />)
    await waitFor(() => expect(getLayers).toHaveBeenCalledOnce())
    await waitFor(() => expect(getLayerTimes).toHaveBeenCalled())
    expect(screen.getByTestId('map-view')).toBeInTheDocument()
    expect(screen.queryByText('区域筛选')).not.toBeInTheDocument()
    expect(screen.queryByText('折线图')).not.toBeInTheDocument()
    expect(screen.queryByText('柱状图')).not.toBeInTheDocument()
    expect(document.querySelector('.right-panel')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the App test and verify RED**

```powershell
npx vitest run src/test/App.test.tsx
```

Expected: FAIL because the current page still renders region filtering and `.right-panel`.

- [ ] **Step 3: Remove App and Sidebar region/chart plumbing**

In `App.tsx`, remove `getRegions`, `Region`, `PointQueryResult`, region/query states, query callbacks, `QueryPanel`, `ChartPanel`, and the `.right-panel` JSX. Load only `getLayers()` on mount. Pass no query callbacks to `MapView` and no region props to `Sidebar`.

In `Sidebar.tsx`, remove `Region`, `regions`, `regionId`, `onRegionChange`, and the entire “区域筛选” section. Keep the “空间查询” hint.

In `ExportPanel.tsx`, remove `regionId` from props, call `getExportCsvUrl(activeLayerId, undefined, startTime, endTime)`, and change the empty hint to `选择图层后可导出数据`.

- [ ] **Step 4: Remove unused frontend API and chart files**

From `frontend/src/services/api.ts`, remove `Region`, `TimeSeriesPoint`, `getRegions`, and `getSeries`. Delete `QueryPanel.tsx` and `ChartPanel.tsx`. Remove `.right-panel`, `.query-panel`, and `.chart-panel` CSS blocks plus their responsive override.

Run:

```powershell
Set-Location frontend
npm uninstall echarts echarts-for-react
```

Add `"test": "vitest run"` to `package.json` scripts.

- [ ] **Step 5: Run frontend tests, lint, and build**

```powershell
npm test
npm run lint
npm run build
```

Expected: all tests pass, lint reports zero errors, and production build exits 0.

- [ ] **Step 6: Review overlapping App.css changes and commit**

```powershell
git diff --check
git diff -- frontend/src/App.css frontend/src/components/MapView.tsx
git status --short
```

Confirm the original flex and `useMemo` changes remain. Stage only files belonging to this feature, inspect `git diff --cached --stat`, then commit with `feat: simplify map queries into floating cards`.

### Task 7: Full verification and browser acceptance

**Files:**
- Modify: `progress.md` and `task_plan.md` only after verification
- Update: `progress.md` and `task_plan.md` after verification

- [ ] **Step 1: Run fresh backend verification**

```powershell
python -m pytest backend/tests -q
python data/validate_data.py
```

Expected: zero failures and no metadata validation errors.

- [ ] **Step 2: Run fresh frontend verification**

```powershell
Set-Location frontend
npm test
npm run lint
npm run build
```

Expected: zero test failures, zero lint errors, and successful production build.

- [ ] **Step 3: Run the application and verify in the in-app browser**

Start FastAPI and Vite in separate terminals:

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173` in the in-app browser and verify:

- SSM tiles visibly use more than two colors and their ramp matches the six legend stops.
- known `NaN`/`-999` areas reveal the basemap;
- point click shows the fixed top-right card;
- Shift-drag automatically shows area loading then statistics;
- closing or changing layer/time clears both card and geometry;
- no region filter, chart, or right panel remains.

- [ ] **Step 4: Inspect the final diff and requirement checklist**

```powershell
git diff --check
git status --short
git diff --stat HEAD
```

Compare the final result line by line with all six user requirements and the approved design. Do not stage unrelated existing files, test images, visual-companion files, or planning ledgers.
