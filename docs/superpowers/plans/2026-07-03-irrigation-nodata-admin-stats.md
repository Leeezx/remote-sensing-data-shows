# Irrigation Page: Nodata Color Alignment & Admin Stats Choropleth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align irrigation nodata background color with SSM page via metadata-driven config, and add admin-region choropleth mode with per-region annual-average coloring, raster hiding, and pixel-query suppression.

**Architecture:** Backend: modify `_render_irrigation_tile` to read `nodataColor`/`nodataOpacity` from layer metadata (mirroring SSM), and add `GET /irrigation/regions/averages` that computes per-region multi-year averages plus a 6-stop dynamic legend via the existing `build_dynamic_legend`. Frontend: extend `MapView` with `disableQuery`, `hideRaster`, `regionColorMap` props; add admin-stats state + JS color interpolation in `IrrigationPage`.

**Tech Stack:** FastAPI, numpy, React+TypeScript, Leaflet/react-leaflet, Vitest+Testing Library, pytest

## Global Constraints

- Default nodata values unchanged: `#e8e8e8` at 50% opacity.
- Legend always 6 stops, computed via 2%-98% percentile range, same as existing `build_dynamic_legend`.
- Time controls frozen (visible but disabled) in admin stats mode, not hidden.
- Village-level stats: existing placeholder behavior preserved (no vector file → "暂未配置" message).

---

### Task 1: Backend — Nodata Color from Layer Metadata

**Files:**
- Modify: `backend/routers/tiles.py:120-137`

**Interfaces:**
- Consumes: `get_irrigation_layer()` from `backend/data_loader.py`
- Produces: `_render_irrigation_tile` now reads `nodataColor`/`nodataOpacity` from layer dict

- [ ] **Step 1: Replace hardcoded nodata color with metadata read**

In `_render_irrigation_tile` (line 127), replace:
```python
nodata_color = (0xE8, 0xE8, 0xE8, 128)
```

With the same pattern used in `_render_ssm_tile` (lines 63-70):
```python
nodata_color_hex = layer.get("nodataColor", "#e8e8e8")
nodata_opacity = float(layer.get("nodataOpacity", 0.5))
try:
    nodata_rgb = tuple(bytes.fromhex(nodata_color_hex.lstrip("#")))
    nodata_alpha = int(round(nodata_opacity * 255))
    nodata_color = (*nodata_rgb, nodata_alpha)
except (ValueError, TypeError):
    nodata_color = (0xE8, 0xE8, 0xE8, 128)
```

- [ ] **Step 2: Verify no behavior change with default values**

Run: `python -m pytest backend/tests/ -v -k irrigation`
Expected: All existing irrigation tests pass (default produces same `rgba(232,232,232,128)`).

- [ ] **Step 3: Commit**

```bash
git add backend/routers/tiles.py
git commit -m "refactor: read irrigation nodata color from layer metadata
"
```

---

### Task 2: Backend — Region Averages Endpoint

**Files:**
- Modify: `backend/irrigation_stats.py`
- Modify: `backend/routers/irrigation.py`
- Create/Modify: `backend/tests/test_irrigation.py`

**Interfaces:**
- Consumes: `get_irrigation_regions()`, `get_irrigation_region_series()` from `backend/data_loader.py`; `build_dynamic_legend` from `backend.ssm_legend`; `get_irrigation_layer()` from `backend.data_loader`
- Produces: `get_irrigation_region_averages(level: str) -> dict` returning `{level, unit, averages: [{regionId, name, average}], legend: [LegendItem]}`; `GET /irrigation/regions/averages?level=county` route

- [ ] **Step 1: Add `get_irrigation_region_averages` function to `backend/irrigation_stats.py`**

Append after the existing `compute_irrigation_region_series` function:

```python
def get_irrigation_region_averages(level: str) -> dict:
    """Return per-region multi-year average irrigation water and a dynamic legend.

    Computes the mean of each region's annual series values, then builds a
    6-stop legend from the distribution of those means using the same
    percentile method as the raster dynamic legend.
    """
    import numpy as np

    from backend.data_loader import (
        get_irrigation_layer,
        get_irrigation_regions,
        get_irrigation_region_series,
    )
    from backend.ssm_legend import build_dynamic_legend

    series_data = get_irrigation_region_series()
    unit = series_data.get("unit", "万m³")
    regions = get_irrigation_regions()
    level_regions = [r for r in regions if r["level"] == level]
    level_series = series_data.get(level, {})

    averages = []
    for region in level_regions:
        region_id = region["id"]
        region_name = region["name"]
        region_entry = level_series.get(region_id, {})
        annual_series = region_entry.get("annual") if isinstance(region_entry, dict) else None
        if annual_series and len(annual_series) > 0:
            avg = sum(float(p["value"]) for p in annual_series) / len(annual_series)
            averages.append({
                "regionId": region_id,
                "name": region_name,
                "average": round(avg, 1),
            })
        else:
            averages.append({
                "regionId": region_id,
                "name": region_name,
                "average": None,
            })

    # Build legend from valid averages
    valid_averages = np.array([a["average"] for a in averages if a["average"] is not None])
    layer = get_irrigation_layer()
    base_legend = layer.get("legend", [])
    if valid_averages.size > 0 and base_legend:
        legend = build_dynamic_legend(valid_averages, base_legend, unit)
    else:
        legend = [dict(item) for item in base_legend]

    return {
        "level": level,
        "unit": unit,
        "averages": averages,
        "legend": legend,
    }
```

- [ ] **Step 2: Add route to `backend/routers/irrigation.py`**

Insert before the `irrigation_regions` function (line 159):

```python
@router.get("/irrigation/regions/averages")
def irrigation_region_averages(level: RegionLevel = Query(...)):
    """Return per-region annual-average irrigation water and a choropleth legend."""
    from backend.irrigation_stats import get_irrigation_region_averages
    return get_irrigation_region_averages(level)
```

- [ ] **Step 3: Write backend tests**

Add to `backend/tests/test_irrigation.py`:

```python
def test_get_irrigation_region_averages_returns_legend_and_averages():
    response = client.get("/api/irrigation/regions/averages?level=county")

    assert response.status_code == 200
    data = response.json()
    assert data["level"] == "county"
    assert data["unit"] == "万m³"
    assert isinstance(data["averages"], list)
    assert len(data["averages"]) > 0
    assert isinstance(data["legend"], list)
    assert len(data["legend"]) == 6
    for item in data["averages"]:
        assert "regionId" in item
        assert "name" in item
        assert "average" in item
    for item in data["legend"]:
        assert "value" in item
        assert "color" in item
        assert "label" in item


def test_get_irrigation_region_averages_legend_has_six_stops():
    response = client.get("/api/irrigation/regions/averages?level=county")

    assert response.status_code == 200
    data = response.json()
    legend = data["legend"]
    assert len(legend) == 6
    # values must be strictly increasing
    values = [item["value"] for item in legend]
    assert all(values[i] < values[i + 1] for i in range(len(values) - 1))
    # colors must be valid hex
    import re
    hex_color = re.compile(r"^#[0-9a-fA-F]{6}$")
    for item in legend:
        assert hex_color.fullmatch(item["color"])


def test_get_irrigation_region_averages_bad_level():
    response = client.get("/api/irrigation/regions/averages?level=province")
    # Literal type validation should reject non-county/non-village
    assert response.status_code == 422
```

- [ ] **Step 4: Run backend tests**

Run: `python -m pytest backend/tests/test_irrigation.py -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/irrigation_stats.py backend/routers/irrigation.py backend/tests/test_irrigation.py
git commit -m "feat: add region averages endpoint for choropleth legend
"
```

---

### Task 3: Frontend — Types and API Client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`

**Interfaces:**
- Produces: `IrrigationRegionAverage`, `IrrigationRegionAveragesResponse` types; `getIrrigationRegionAverages(level) -> Promise<IrrigationRegionAveragesResponse>`

- [ ] **Step 1: Add types to `frontend/src/types/index.ts`**

Insert after `IrrigationVectorGeoJSON` (line 84):

```typescript
export interface IrrigationRegionAverage {
  regionId: string
  name: string
  average: number | null
}

export interface IrrigationRegionAveragesResponse {
  level: IrrigationRegionLevel
  unit: string
  averages: IrrigationRegionAverage[]
  legend: LegendItem[]
}
```

- [ ] **Step 2: Add API function to `frontend/src/services/api.ts`**

Insert after `getIrrigationVectorGeoJSON` (line 131), before the `// ===== Spatial Queries =====` comment:

```typescript
export async function getIrrigationRegionAverages(
  level: IrrigationRegionLevel,
): Promise<IrrigationRegionAveragesResponse> {
  const { data } = await client.get<IrrigationRegionAveragesResponse>(
    '/irrigation/regions/averages',
    { params: { level } },
  )
  return data
}
```

Also add the import for `IrrigationRegionAveragesResponse` at the top (line 9-16): add `IrrigationRegionAveragesResponse` to the import from `'../types'`.

- [ ] **Step 3: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat: add types and API client for region averages
"
```

---

### Task 4: Frontend — MapView Props Extension

**Files:**
- Modify: `frontend/src/components/MapView.tsx`

**Interfaces:**
- Consumes: `LegendItem` from `../types`
- Produces: `MapViewProps` gains `disableQuery?: boolean`, `hideRaster?: boolean`, `regionColorMap?: Map<string, string> | null`; `TileOverlay` gains `visible` support; `MapEvents` `enabled` includes `!disableQuery`; `RegionOverlay` uses `colorMap` for fill color

- [ ] **Step 1: Add new props to `MapViewProps` interface**

At line 227-235, modify:

```typescript
interface MapViewProps {
  layers: Layer[]
  activeLayerId: string | null
  opacity: number
  currentTime: string
  regionVector?: IrrigationVectorGeoJSON | null
  selectedRegionId?: string | null
  onRegionSelect?: (region: { id: string; name: string }) => void
  disableQuery?: boolean
  hideRaster?: boolean
  regionColorMap?: Map<string, string> | null
}
```

- [ ] **Step 2: Destructure new props in `MapView` function**

At line 237-245, update destructuring:

```typescript
export default function MapView({
  layers,
  activeLayerId,
  opacity,
  currentTime,
  regionVector = null,
  selectedRegionId = null,
  onRegionSelect,
  disableQuery = false,
  hideRaster = false,
  regionColorMap = null,
}: MapViewProps) {
```

- [ ] **Step 3: Guard TileOverlay with `hideRaster`**

At line 303, wrap TileOverlay:

```tsx
{!hideRaster && (
  <TileOverlay layer={activeLayer} time={currentTime} opacity={opacity} />
)}
```

- [ ] **Step 4: Add `regionColorMap` prop to RegionOverlay**

At line 305-309, update:

```tsx
<RegionOverlay
  data={regionVector}
  selectedRegionId={selectedRegionId}
  onRegionSelect={onRegionSelect}
  colorMap={regionColorMap}
/>
```

- [ ] **Step 5: Add `disableQuery` to MapEvents**

At line 312-316, update:

```tsx
<MapEvents
  enabled={Boolean(activeLayerId && currentTime && !disableQuery)}
  onPointCoords={handlePointCoords}
  onAreaCoords={handleAreaCoords}
/>
```

- [ ] **Step 6: Update RegionOverlay to accept and use `colorMap`**

Modify the `RegionOverlay` component (lines 158-214):

```typescript
function RegionOverlay({
  data,
  selectedRegionId,
  onRegionSelect,
  colorMap,
}: {
  data: IrrigationVectorGeoJSON | null
  selectedRegionId?: string | null
  onRegionSelect?: (region: { id: string; name: string }) => void
  colorMap?: Map<string, string> | null
}) {
  if (!data || !onRegionSelect) return null

  const featureStyle = (feature?: { properties?: Record<string, unknown> }) => {
    const featureId = String(
      feature?.properties?.id ??
      feature?.properties?.gb ??
      feature?.properties?.name ??
      '',
    )
    const selected = featureId && featureId === selectedRegionId
    // Use colorMap for choropleth fill; fall back to default blue
    const fillFromMap = colorMap?.get(featureId)
    const hasColorMap = colorMap !== null && colorMap !== undefined && colorMap.size > 0
    return {
      color: selected ? '#b45309' : (hasColorMap ? '#334155' : '#1d4ed8'),
      opacity: selected ? 0.75 : (hasColorMap ? 0.7 : 0.42),
      weight: selected ? 2.6 : (hasColorMap ? 1.0 : 1.2),
      fillColor: selected ? '#f59e0b' : (fillFromMap ?? '#60a5fa'),
      fillOpacity: selected ? 0.4 : (hasColorMap ? 0.65 : 0.035),
    }
  }
  // ... rest of component unchanged: return <GeoJSON> with same event handlers
```

- [ ] **Step 7: Verify TypeScript compilation**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "feat: add disableQuery, hideRaster, regionColorMap props to MapView
"
```

---

### Task 5: Frontend — IrrigationPage Admin Stats Mode

**Files:**
- Modify: `frontend/src/pages/IrrigationPage.tsx`
- Modify: `frontend/src/test/App.test.tsx`

**Interfaces:**
- Consumes: `getIrrigationRegionAverages` from `../services/api`; `MapView` new props; `Legend` existing interface
- Produces: Admin stats state management, color interpolation, legend switching, time control freezing

- [ ] **Step 1: Add color interpolation utility**

Insert after the `formatTime` function (before `SeriesChart`):

```typescript
/** Interpolate a value into a hex color using legend stops (emulates np.interp). */
function interpolateColor(value: number, legend: LegendItem[]): string {
  if (legend.length === 0) return '#cccccc'
  // legend expected sorted ascending by value
  const stops = [...legend].sort((a, b) => a.value - b.value)
  if (value <= stops[0].value) return stops[0].color
  if (value >= stops[stops.length - 1].value) return stops[stops.length - 1].color

  // Find bracket
  let lo = stops[0], hi = stops[stops.length - 1]
  for (let i = 0; i < stops.length - 1; i++) {
    if (value >= stops[i].value && value <= stops[i + 1].value) {
      lo = stops[i]
      hi = stops[i + 1]
      break
    }
  }

  const t = (value - lo.value) / (hi.value - lo.value)
  const toByte = (hex: string, offset: number) => parseInt(hex.slice(1 + offset * 2, 3 + offset * 2), 16)
  const r = Math.round(toByte(lo.color, 0) + t * (toByte(hi.color, 0) - toByte(lo.color, 0)))
  const g = Math.round(toByte(lo.color, 1) + t * (toByte(hi.color, 1) - toByte(lo.color, 1)))
  const b = Math.round(toByte(lo.color, 2) + t * (toByte(hi.color, 2) - toByte(lo.color, 2)))
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}
```

- [ ] **Step 2: Add admin stats state and import**

Add to imports (line 1-23):
```typescript
import {
  getIrrigationRegionAverages,
  // ... existing imports
} from '../services/api'
import type {
  IrrigationRegionAverage,
  IrrigationRegionAveragesResponse,
  // ... existing imports
} from '../types'
```

Add new state variables after line 107 (`seriesError`):

```typescript
const [adminAverages, setAdminAverages] = useState<IrrigationRegionAverage[]>([])
const [adminLegend, setAdminLegend] = useState<LegendItem[]>([])
const [adminStatsLoading, setAdminStatsLoading] = useState(false)
```

- [ ] **Step 3: Modify regionLevel effect to fetch averages**

In the `useEffect` at line 163, add the averages fetch after the GeoJSON fetch. Modify the effect (lines 163-205) to include:

After the existing `getIrrigationVectorGeoJSON(regionLevel)` chain (where `setRegionVector(data)` is called at line 189), add a second chain:

```typescript
// After setting regionVector, also fetch averages
getIrrigationRegionAverages(regionLevel)
  .then((avgData) => {
    if (!cancelled) {
      setAdminAverages(avgData.averages)
      setAdminLegend(avgData.legend)
      setAdminStatsLoading(false)
    }
  })
  .catch(() => {
    if (!cancelled) {
      setAdminAverages([])
      setAdminLegend([])
      setAdminStatsLoading(false)
    }
  })
```

And at the start of the effect, set loading:
```typescript
setAdminStatsLoading(true)
```

And in the early return (when `!regionLevel`), also clear admin state:
```typescript
setAdminAverages([])
setAdminLegend([])
setAdminStatsLoading(false)
```

- [ ] **Step 4: Compute colorMap for MapView**

Add a `useMemo` to compute the `regionColorMap` from `adminAverages` and `adminLegend`:

```typescript
const regionColorMap = useMemo(() => {
  if (adminAverages.length === 0 || adminLegend.length === 0) return null
  const map = new Map<string, string>()
  for (const item of adminAverages) {
    if (item.average !== null) {
      map.set(item.regionId, interpolateColor(item.average, adminLegend))
    }
  }
  return map
}, [adminAverages, adminLegend])

const isAdminStatsMode = regionLevel !== null && adminAverages.length > 0
```

- [ ] **Step 5: Pass new props to MapView**

Update the `<MapView>` element (lines 346-354):

```tsx
<MapView
  layers={layer ? [layer] : []}
  activeLayerId={layer?.id ?? null}
  opacity={opacity}
  currentTime={currentTime}
  regionVector={regionVector}
  selectedRegionId={selectedRegion?.id ?? null}
  onRegionSelect={setSelectedRegion}
  disableQuery={isAdminStatsMode}
  hideRaster={isAdminStatsMode}
  regionColorMap={regionColorMap}
/>
```

- [ ] **Step 6: Freeze time controls in admin stats mode**

Update the resolution toggle buttons (lines 258-270):

```tsx
<button
  className={`btn btn-sm ${rasterResolution === 'annual' ? 'btn-primary' : ''}`}
  onClick={() => setRasterResolution('annual')}
  disabled={isAdminStatsMode}
>
  年度
</button>
<button
  className={`btn btn-sm ${rasterResolution === 'month' ? 'btn-primary' : ''}`}
  onClick={() => setRasterResolution('month')}
  disabled={isAdminStatsMode}
>
  月度
</button>
```

Update the timeline prev/next buttons (lines 273-295) by adding `disabled={isAdminStatsMode}` to both `<button>` elements.

- [ ] **Step 7: Switch legend in admin stats mode**

Update the `<Legend>` element (lines 357-361):

```tsx
<Legend
  layer={layer}
  items={
    isAdminStatsMode
      ? adminLegend
      : (legendState.key === `irrigation_water:${currentTime}` ? legendState.items : [])
  }
  status={
    isAdminStatsMode
      ? 'ready'
      : (legendState.key === `irrigation_water:${currentTime}` ? legendState.status : 'loading')
  }
/>
```

- [ ] **Step 8: Show admin stats loading state in the right sidebar**

In the right sidebar stats section (lines 364-402), add a loading state for admin stats:

Replace the section's initial content to also handle `adminStatsLoading`:
In the `{!regionLevel ? ...}` branch at line 394, nothing changes ("未开启行政区统计"). For the `selectedRegion` branches, they remain unchanged. For the loading state (line 392-393), keep as is.

- [ ] **Step 9: Update frontend tests**

In `frontend/src/test/App.test.tsx`, add mock for `getIrrigationRegionAverages`:

Add to `apiMocks` (the `vi.hoisted` block at line 7-19):
```typescript
getIrrigationRegionAverages: vi.fn(),
```

Add to the `vi.mock` factory (line 21-27):
```typescript
getIrrigationRegionAverages: apiMocks.getIrrigationRegionAverages,
```

Add mock implementation in `beforeEach`:

Find the `beforeEach` block in the test file and add:
```typescript
apiMocks.getIrrigationRegionAverages.mockResolvedValue({
  level: 'county',
  unit: '万m³',
  averages: [
    { regionId: 'county_a', name: '示范县A', average: 1480.5 },
    { regionId: 'county_b', name: '示范县B', average: 320.0 },
  ],
  legend: [
    { value: 100, color: '#eff3ff', label: '100 万m³' },
    { value: 400, color: '#bdd7e7', label: '400 万m³' },
    { value: 700, color: '#6baed6', label: '700 万m³' },
    { value: 1000, color: '#3182bd', label: '1000 万m³' },
    { value: 1300, color: '#08519c', label: '1300 万m³' },
    { value: 1600, color: '#042d60', label: '1600 万m³' },
  ],
})
```

Add a test for admin stats mode transitions at the end of the describe block:

```typescript
it('shows admin stats controls when county statistics is enabled', async () => {
  render(<App />)
  // Navigate to irrigation page
  const irrigationLink = screen.getByText('灌溉用水')
  await userEvent.click(irrigationLink)
  await waitFor(() => {
    expect(screen.getByText('县级统计')).toBeInTheDocument()
  })
  // Click admin stats button
  const countyBtn = screen.getByText('县级统计')
  await userEvent.click(countyBtn)
  // After click, averages should have been requested
  await waitFor(() => {
    expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county')
  })
  // Click again to disable
  await userEvent.click(countyBtn)
  // Should restore to initial state
  await waitFor(() => {
    expect(screen.getByText('未开启行政区统计')).toBeInTheDocument()
  })
})
```

- [ ] **Step 10: Run frontend tests**

Run: `cd frontend && npx vitest run src/test/App.test.tsx`
Expected: All tests pass.

- [ ] **Step 11: Run full TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: No type errors.

- [ ] **Step 12: Commit**

```bash
git add frontend/src/pages/IrrigationPage.tsx frontend/src/test/App.test.tsx
git commit -m "feat: admin stats choropleth mode with legend switching and time freeze
"
```

---

### Final Verification

- [ ] Run all backend tests: `python -m pytest backend/tests/ -v`
- [ ] Run all frontend tests: `cd frontend && npx vitest run`
- [ ] Run production build: `cd frontend && npm run build`
- [ ] Manual browser verification:
  1. Open irrigation page, confirm raster displays with nodata background.
  2. Toggle between annual/monthly, confirm raster updates.
  3. Click "县级统计" → raster hides, vector polygons appear colored by annual average, legend switches, time controls disabled, map clicks do nothing.
  4. Click a county → right sidebar shows stats + charts.
  5. Click "县级统计" again → raster returns, pixel query works, legend restores, time controls re-enabled.

- [ ] Inspect `git status --short` and summarize changed files.
