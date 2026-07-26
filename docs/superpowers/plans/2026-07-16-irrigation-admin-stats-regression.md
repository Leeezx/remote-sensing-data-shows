# 灌溉行政区统计交互回归修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复灌溉县/乡镇统计模式的查询开关、县级年平均着色和乡镇双层下钻回归，同时保留按县分片性能约束。

**Architecture:** 将“统计模式是否开启”与“统计数据是否就绪”分离；`IrrigationPage` 长期维护县级底层并按需维护一个县的乡镇详情层，`MapView` 顺序渲染两层并在统计模式开启时清理栅格查询。后端从合并后的县/乡镇 series 重建稳定区域目录，避免单级预计算覆盖另一行政级别。

**Tech Stack:** Python 3、FastAPI、pytest、React 19、TypeScript、React-Leaflet/Leaflet、Vitest、Testing Library、Vite、Oxlint。

## Global Constraints

- 不恢复全国乡镇全量 GeoJSON 或无 `countyId` 的全国乡镇平均值请求。
- 乡镇分片继续执行小于 1,000,000 bytes、最多 499 个要素的前后端保护。
- 县级与乡镇图例分别计算数值阈值，但共同使用灌溉栅格的六级百分位算法、颜色顺序和插值规则。
- 统计模式开启后，即使矢量或 averages 请求失败，也必须保持栅格隐藏、查询禁用。
- 当前工作区有大量既有未提交修改；每次提交前必须执行 `git diff --cached --name-only` 和 `git diff --cached --check`，不得带入任务清单外文件。
- 不修改与灌溉行政区统计无关的认证、导出、外部栅格或其他页面逻辑。

---

## File Structure

- `backend/precompute_irrigation.py`：新增纯区域目录构建函数和只刷新区域目录的 CLI 路径；正常预计算也使用合并目录。
- `backend/tests/test_precompute_irrigation.py`：隔离测试两级保留、去重、稳定排序和 `parentId` 保留，不读取真实 Shapefile。
- `data/stats/irrigation_regions.json`：用修复后的 CLI 从现有完整 series 恢复县级元数据。
- `backend/tests/test_irrigation.py`：保留并加强县级 regions/averages、乡镇按县过滤契约。
- `frontend/src/components/Legend.tsx`：兼容原单组接口并新增命名分组图例。
- `frontend/src/test/Legend.test.tsx`：覆盖两组图例及每组独立状态。
- `frontend/src/App.css`：为紧凑分组图例增加标题和分隔样式。
- `frontend/src/components/MapView.tsx`：支持县级主层和乡镇详情层；禁用查询时清除查询状态与绘制状态。
- `frontend/src/test/MapView.test.tsx`：覆盖双层顺序、详情层事件、query reset 和既有 499 上限。
- `frontend/src/pages/IrrigationPage.tsx`：拆分县/乡镇矢量、averages、legend、加载状态和请求序号。
- `frontend/src/test/App.test.tsx`：覆盖即时禁用、县级着色、双层共存、跨县切换、失败保留与乱序响应。

---

### Task 1: Preserve Both Administrative Levels in the Region Catalog

**Files:**
- Modify: `backend/precompute_irrigation.py:31-290`
- Create: `backend/tests/test_precompute_irrigation.py`

**Interfaces:**
- Produces: `build_region_catalog(series_data: dict, previous_regions: list[dict] | None = None) -> list[dict]`
- Produces: `_publish_region_catalog(series_data: dict) -> list[dict]`
- Consumes later: Task 6 runs `python backend/precompute_irrigation.py --regions-only`.

- [ ] **Step 1: Write failing pure-function tests**

Create `backend/tests/test_precompute_irrigation.py`:

```python
from backend.precompute_irrigation import build_region_catalog


def test_build_region_catalog_preserves_both_levels_and_parent_ids():
    series_data = {
        "unit": "万m³",
        "county": {
            "county_b": {"name": "乙县", "annual": [], "monthly": []},
            "county_a": {"name": "甲县", "annual": [], "monthly": []},
        },
        "township": {
            "township_a2": {"name": "乙镇", "annual": [], "monthly": []},
            "township_a1": {"name": "甲镇", "annual": [], "monthly": []},
        },
    }
    previous = [
        {
            "id": "township_a1",
            "name": "旧名称",
            "level": "township",
            "parentId": "county_a",
        }
    ]

    assert build_region_catalog(series_data, previous) == [
        {"id": "county_a", "name": "甲县", "level": "county", "parentId": None},
        {"id": "county_b", "name": "乙县", "level": "county", "parentId": None},
        {
            "id": "township_a1",
            "name": "甲镇",
            "level": "township",
            "parentId": "county_a",
        },
        {
            "id": "township_a2",
            "name": "乙镇",
            "level": "township",
            "parentId": None,
        },
    ]


def test_build_region_catalog_ignores_unknown_sections_and_invalid_entries():
    series_data = {
        "unit": "万m³",
        "county": {"county_a": {"name": "甲县"}, "broken": "not-an-object"},
        "township": {},
        "province": {"province_a": {"name": "甲省"}},
    }

    assert build_region_catalog(series_data) == [
        {"id": "county_a", "name": "甲县", "level": "county", "parentId": None}
    ]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_precompute_irrigation.py -v -p no:cacheprovider
```

Expected: collection fails because `build_region_catalog` does not exist.

- [ ] **Step 3: Implement the pure catalog builder**

Add above `main()` in `backend/precompute_irrigation.py`:

```python
def build_region_catalog(
    series_data: dict,
    previous_regions: list[dict] | None = None,
) -> list[dict]:
    """Build a stable county+township catalog from merged series data."""
    previous_by_key = {
        (str(region.get("level", "")), str(region.get("id", ""))): region
        for region in (previous_regions or [])
        if isinstance(region, dict)
    }
    catalog: list[dict] = []
    for level in ("county", "township"):
        level_data = series_data.get(level, {})
        if not isinstance(level_data, dict):
            continue
        for region_id in sorted(str(key) for key in level_data):
            entry = level_data.get(region_id)
            if not isinstance(entry, dict):
                continue
            previous = previous_by_key.get((level, region_id), {})
            catalog.append({
                "id": region_id,
                "name": str(entry.get("name") or region_id),
                "level": level,
                "parentId": previous.get("parentId"),
            })
    return catalog


def _load_previous_regions() -> list[dict]:
    if not REGIONS_PATH.is_file():
        return []
    try:
        payload = json.loads(REGIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _publish_region_catalog(series_data: dict) -> list[dict]:
    previous = _load_previous_regions()
    catalog = build_region_catalog(series_data, previous)
    if catalog != previous:
        _write_json(REGIONS_PATH, catalog)
    return catalog
```

Do not leave the old `regions = []` loop at the bottom of `main()`; replace it with `_publish_region_catalog(existing)` so normal county and township runs always publish both levels.

- [ ] **Step 4: Add and implement the regions-only CLI path**

Add this argparse option:

```python
parser.add_argument(
    "--regions-only",
    action="store_true",
    help="Rebuild irrigation_regions.json from existing series without reading shapefiles",
)
```

Load `existing` before the Shapefile existence check. Immediately after loading it, add:

```python
if args.regions_only:
    catalog = _publish_region_catalog(existing)
    print(f"Published {len(catalog)} regions to {REGIONS_PATH}")
    return
```

The Shapefile check and feature processing must run only after this return path.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_precompute_irrigation.py -v -p no:cacheprovider
```

Expected: 2 tests pass without reading F: or real statistics files.

- [ ] **Step 6: Commit the backend catalog code and tests**

```powershell
git add -- backend/precompute_irrigation.py backend/tests/test_precompute_irrigation.py
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: preserve irrigation region catalog levels"
```

Expected staged files: exactly the two files listed above.

---

### Task 2: Add Backward-Compatible Grouped Legends

**Files:**
- Modify: `frontend/src/components/Legend.tsx:3-40`
- Modify: `frontend/src/test/Legend.test.tsx`
- Modify: `frontend/src/App.css:376-420`

**Interfaces:**
- Produces: exported `LegendGroup` with `{ title: string; items: LegendItem[]; status?: LegendStatus }`.
- Produces: optional `LegendProps.groups?: LegendGroup[]` while preserving existing `items/status` behavior.
- Consumes later: Task 5 passes county and township legend groups from `IrrigationPage`.

- [ ] **Step 1: Write failing grouped-legend tests**

Append to `frontend/src/test/Legend.test.tsx`:

```tsx
it('renders separately titled county and township legend groups', () => {
  render(
    <Legend
      layer={layer}
      groups={[
        {
          title: '县级年平均',
          items: [{ value: 100, color: '#111111', label: '县级 100' }],
          status: 'ready',
        },
        {
          title: '当前县乡镇年平均',
          items: [{ value: 10, color: '#222222', label: '乡镇 10' }],
          status: 'ready',
        },
      ]}
    />,
  )

  expect(screen.getByRole('heading', { name: '县级年平均' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '当前县乡镇年平均' })).toBeInTheDocument()
  expect(screen.getByText('县级 100')).toBeInTheDocument()
  expect(screen.getByText('乡镇 10')).toBeInTheDocument()
})

it('shows an error only inside the failed legend group', () => {
  render(
    <Legend
      layer={layer}
      groups={[
        { title: '县级年平均', items: [], status: 'error' },
        {
          title: '当前县乡镇年平均',
          items: [{ value: 10, color: '#222222', label: '乡镇 10' }],
          status: 'ready',
        },
      ]}
    />,
  )

  expect(screen.getByRole('alert')).toHaveTextContent('图例暂不可用')
  expect(screen.getByText('乡镇 10')).toBeInTheDocument()
})
```

- [ ] **Step 2: Run the Legend tests and verify RED**

Run from `frontend`:

```powershell
npx vitest run src/test/Legend.test.tsx
```

Expected: TypeScript/runtime failure because `groups` is not a `Legend` prop.

- [ ] **Step 3: Implement grouped rendering without changing single-group callers**

In `Legend.tsx`, export:

```tsx
export interface LegendGroup {
  title: string
  items: LegendItem[]
  status?: LegendStatus
}
```

Add `groups?: LegendGroup[]` to `LegendProps`. Extract a local renderer:

```tsx
function LegendBody({ items, status }: { items: LegendItem[]; status: LegendStatus }) {
  if (status === 'loading') {
    return <div className="legend-status" role="status" aria-live="polite">正在加载图例...</div>
  }
  if (status === 'error') {
    return <div className="legend-status" role="alert">图例暂不可用</div>
  }
  return (
    <div className="legend-items">
      {items.map((item) => (
        <div key={`${item.value}:${item.color}`} className="legend-item">
          <span className="legend-color" style={{ backgroundColor: item.color }} />
          <span className="legend-label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
```

Inside `Legend`, render `groups` when it is a non-empty array:

```tsx
{groups && groups.length > 0 ? (
  <div className="legend-groups">
    {groups.map((group) => (
      <section className="legend-group" key={group.title}>
        <h5>{group.title}</h5>
        <LegendBody items={group.items} status={group.status ?? 'ready'} />
      </section>
    ))}
  </div>
) : (
  <LegendBody items={items} status={status} />
)}
```

- [ ] **Step 4: Add compact group styling**

Add to `App.css` after `.legend h4`:

```css
.legend-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.legend-group + .legend-group {
  border-top: 1px solid rgba(51, 65, 85, 0.18);
  padding-top: 7px;
}

.legend-group h5 {
  margin: 0 0 4px;
  color: #334155;
  font-size: 12px;
}
```

- [ ] **Step 5: Run tests and verify GREEN**

```powershell
npx vitest run src/test/Legend.test.tsx
```

Expected: all existing single-group tests and both new grouped tests pass.

- [ ] **Step 6: Commit grouped Legend support**

```powershell
git add -- frontend/src/components/Legend.tsx frontend/src/test/Legend.test.tsx frontend/src/App.css
git diff --cached --name-only
git diff --cached --check
git commit -m "feat: support grouped map legends"
```

---

### Task 3: Clear Raster Queries and Render Two Region Overlays

**Files:**
- Modify: `frontend/src/components/MapView.tsx:50-465`
- Modify: `frontend/src/test/MapView.test.tsx`

**Interfaces:**
- Preserves: existing primary props `regionVector`, `selectedRegionId`, `onRegionSelect`, `regionColorMap`, `regionLevel`.
- Produces: `detailRegionVector`, `detailSelectedRegionId`, `onDetailRegionSelect`, `detailRegionColorMap`, `detailRegionLevel` with the corresponding existing types.
- Behavior: primary overlay renders first; detail overlay renders second and is therefore interactive above it.

- [ ] **Step 1: Extend the GeoJSON mock and write a failing dual-layer test**

Change the mock bookkeeping in `MapView.test.tsx` from a single count to an array:

```tsx
geoJsonFeatureIds: [] as string[][],
```

In the mocked `GeoJSON`, append IDs and expose the first ID:

```tsx
const ids = data.features.map((feature) => feature.properties.id)
mapMocks.geoJsonFeatureIds.push(ids)
return (
  <div
    data-testid="region-geojson"
    data-first-feature-id={ids[0] ?? ''}
    data-feature-count={data.features.length}
  />
)
```

Add this test:

```tsx
it('keeps the county overlay while mounting the township detail overlay above it', () => {
  const county = {
    type: 'FeatureCollection' as const,
    features: [{
      type: 'Feature' as const,
      properties: { id: 'county_a', name: '示范县A' },
      geometry: { type: 'Polygon' as const, coordinates: [[[100, 30], [101, 30], [100, 30]]] },
    }],
  }
  const township = {
    type: 'FeatureCollection' as const,
    features: [{
      type: 'Feature' as const,
      properties: { id: 'township_a1', name: '示范镇A1' },
      geometry: { type: 'Polygon' as const, coordinates: [[[100, 30], [100.5, 30], [100, 30]]] },
    }],
  }

  render(
    <MapView
      {...baseProps}
      regionVector={county}
      regionLevel="county"
      onRegionSelect={vi.fn()}
      detailRegionVector={township}
      detailRegionLevel="township"
      onDetailRegionSelect={vi.fn()}
    />,
  )

  expect(mapMocks.geoJsonFeatureIds).toEqual([['county_a'], ['township_a1']])
  expect(screen.getAllByTestId('region-geojson')).toHaveLength(2)
  expect(mapMocks.map.fitBounds).toHaveBeenCalledOnce()
})
```

- [ ] **Step 2: Write a failing query-reset test**

```tsx
it('clears an existing point result when administrative statistics disables queries', async () => {
  mockedQueryPoint.mockResolvedValueOnce({
    layerId: 'ndvi', time: '2025-06', lng: 116, lat: 39, value: 0.5, unit: '指数',
  })
  const { rerender } = render(<MapView {...baseProps} />)

  act(() => mapMocks.handlers!.click?.({ latlng: { lat: 39, lng: 116 } }))
  expect(await screen.findByRole('heading', { name: '点查询结果' })).toBeInTheDocument()

  rerender(<MapView {...baseProps} disableQuery />)

  expect(screen.queryByRole('heading', { name: '点查询结果' })).not.toBeInTheDocument()
  act(() => mapMocks.handlers!.click?.({ latlng: { lat: 40, lng: 117 } }))
  expect(mockedQueryPoint).toHaveBeenCalledOnce()
})
```

- [ ] **Step 3: Run MapView tests and verify RED**

```powershell
npx vitest run src/test/MapView.test.tsx
```

Expected: dual-layer props do not exist and disabling queries leaves the old query card visible.

- [ ] **Step 4: Add detail overlay props and render order**

Extend `MapViewProps` and destructuring:

```tsx
detailRegionVector?: IrrigationVectorGeoJSON | null
detailSelectedRegionId?: string | null
onDetailRegionSelect?: (region: { id: string; name: string }) => void
detailRegionColorMap?: Map<string, string> | null
detailRegionLevel?: string | null
```

Render the existing primary `RegionOverlay` unchanged, then immediately render:

```tsx
<RegionOverlay
  data={detailRegionVector}
  selectedRegionId={detailSelectedRegionId}
  onRegionSelect={onDetailRegionSelect}
  colorMap={detailRegionColorMap}
  regionLevel={detailRegionLevel}
/>
```

- [ ] **Step 5: Reset query state and in-progress drawing when disabled**

In `MapView`, add:

```tsx
useEffect(() => {
  if (!disableQuery) return
  reset()
  setMarker(null)
  setRect(null)
}, [disableQuery, reset])
```

In `MapEvents`, add an effect that ends an active drawing when `enabled` becomes false:

```tsx
useEffect(() => {
  if (enabled || !drawingRef.current) return
  drawingRef.current = false
  rectRef.current = []
  removeGlobalMouseupListener()
  map.dragging.enable()
}, [enabled, map, removeGlobalMouseupListener])
```

- [ ] **Step 6: Run MapView tests and verify GREEN**

```powershell
npx vitest run src/test/MapView.test.tsx
```

Expected: new tests pass; the 81-feature timing and 500-feature rejection tests remain green after adapting their count assertion to `geoJsonFeatureIds`.

- [ ] **Step 7: Commit MapView changes**

```powershell
git add -- frontend/src/components/MapView.tsx frontend/src/test/MapView.test.tsx
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: preserve county overlay during township drilldown"
```

---

### Task 4: Make Statistics Mode Immediate and Restore County Coloring

**Files:**
- Modify: `frontend/src/pages/IrrigationPage.tsx:115-550`
- Modify: `frontend/src/test/App.test.tsx:1-350`

**Interfaces:**
- Produces page state: `countyVector`, `countyAverages`, `countyLegend`, `countyLegendStatus`, `countyColorMap`.
- Uses: Task 3 primary region props for the county layer.
- Uses: `isAdminStatsMode = regionLevel !== null` only.

- [ ] **Step 1: Expand the MapView page-test mock**

Add a hoisted holder:

```tsx
const mapViewMocks = vi.hoisted(() => ({ props: null as Record<string, unknown> | null }))
```

Extend the existing type import with `IrrigationRegionAveragesResponse` and `IrrigationVectorGeoJSON` for deferred fixtures used below.

Update the `MapView` mock to store props and expose flags:

```tsx
default: (props: {
  onRegionSelect?: (region: { id: string; name: string }) => void
  onDetailRegionSelect?: (region: { id: string; name: string }) => void
  regionVector?: unknown
  detailRegionVector?: unknown
  disableQuery?: boolean
  hideRaster?: boolean
  regionColorMap?: Map<string, string> | null
}) => {
  mapViewMocks.props = props
  return (
    <div data-testid="map-view">
      <span data-testid="query-disabled">{String(Boolean(props.disableQuery))}</span>
      <span data-testid="raster-hidden">{String(Boolean(props.hideRaster))}</span>
      <span data-testid="county-layer">{props.regionVector ? 'loaded' : 'empty'}</span>
      <span data-testid="township-layer">{props.detailRegionVector ? 'loaded' : 'empty'}</span>
      <button onClick={() => props.onRegionSelect?.({ id: 'county_a', name: '示范县A' })}>选择示范县A</button>
      <button onClick={() => props.onRegionSelect?.({ id: 'county_b', name: '示范县B' })}>选择示范县B</button>
      <button onClick={() => props.onDetailRegionSelect?.({ id: 'township_a1', name: '示范镇A1' })}>选择示范镇A1</button>
    </div>
  )
},
```

- [ ] **Step 2: Write a failing immediate-disable test**

```tsx
it('disables raster queries immediately while county averages are still loading', async () => {
  window.history.pushState({}, '', '/irrigation')
  const averages = deferred<IrrigationRegionAveragesResponse>()
  apiMocks.getIrrigationRegionAverages.mockReturnValueOnce(averages.promise)
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '县级统计' }))

  expect(screen.getByTestId('query-disabled')).toHaveTextContent('true')
  expect(screen.getByTestId('raster-hidden')).toHaveTextContent('true')
  expect(screen.getByRole('button', { name: '年度' })).toBeDisabled()
})
```

- [ ] **Step 3: Write a failing county-coloring test**

```tsx
it('keeps county statistics mode active and colors counties after averages arrive', async () => {
  window.history.pushState({}, '', '/irrigation')
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '县级统计' }))
  await waitFor(() => expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county'))
  await waitFor(() => {
    const colorMap = mapViewMocks.props?.regionColorMap as Map<string, string> | null
    expect(colorMap?.has('county_a')).toBe(true)
    expect(colorMap?.has('county_b')).toBe(true)
  })
  expect(screen.getByRole('heading', { name: '县级年平均' })).toBeInTheDocument()
})
```

Add an explicit failure-path test so data failure cannot reactivate raster queries:

```tsx
it('keeps raster queries disabled when county averages fail', async () => {
  window.history.pushState({}, '', '/irrigation')
  apiMocks.getIrrigationRegionAverages.mockRejectedValueOnce(new Error('averages unavailable'))
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '县级统计' }))
  await waitFor(() => expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county'))

  expect(screen.getByTestId('query-disabled')).toHaveTextContent('true')
  expect(screen.getByTestId('raster-hidden')).toHaveTextContent('true')
  expect(screen.getByRole('alert')).toHaveTextContent('图例暂不可用')
})
```

- [ ] **Step 4: Run both tests and verify RED**

```powershell
npx vitest run src/test/App.test.tsx -t "disables raster queries immediately|keeps county statistics mode active|keeps raster queries disabled"
```

Expected: immediate flags remain false because `isAdminStatsMode` still depends on averages; grouped county heading is absent.

- [ ] **Step 5: Split county state and load it for both admin modes**

Replace the single `regionVector/adminAverages/adminLegend` state with:

```tsx
const [countyVector, setCountyVector] = useState<IrrigationVectorGeoJSON | null>(null)
const [countyAverages, setCountyAverages] = useState<IrrigationRegionAverage[]>([])
const [countyLegend, setCountyLegend] = useState<LegendItem[]>([])
const [countyLegendStatus, setCountyLegendStatus] = useState<LegendStatus>('loading')
```

The initial admin-layer effect must:

1. clear selection/detail state when `regionLevel` changes;
2. request `getIrrigationVectorStatus(regionLevel)`;
3. load `loadVector('county')` and assign `countyVector`;
4. independently request `getIrrigationRegionAverages('county')` for both county and township modes;
5. set only `countyLegendStatus='error'` if averages fail—do not mark the vector unavailable.

Define:

```tsx
const isAdminStatsMode = regionLevel !== null

const countyColorMap = useMemo(
  () => buildRegionColorMap(countyAverages, countyLegend),
  [countyAverages, countyLegend],
)
```

Rename the current inline color-map loop to a file-local helper:

```tsx
function buildRegionColorMap(
  averages: IrrigationRegionAverage[],
  legend: LegendItem[],
): Map<string, string> | null {
  if (averages.length === 0 || legend.length === 0) return null
  const result = new Map<string, string>()
  for (const item of averages) {
    if (item.average !== null) result.set(item.regionId, interpolateColor(item.average, legend))
  }
  return result.size > 0 ? result : null
}
```

- [ ] **Step 6: Pass county props and a one-group county legend**

For both admin modes pass the county layer as the primary layer:

```tsx
regionVector={isAdminStatsMode ? countyVector : null}
regionLevel={isAdminStatsMode ? 'county' : null}
regionColorMap={countyColorMap}
disableQuery={isAdminStatsMode}
hideRaster={isAdminStatsMode}
```

When `regionLevel` is non-null but no township detail is loaded, pass:

```tsx
groups={[{
  title: '县级年平均',
  items: countyLegend,
  status: countyLegendStatus,
}]}
```

Raster mode continues using the existing single `items/status` props.

- [ ] **Step 7: Run the focused and full page tests**

```powershell
npx vitest run src/test/App.test.tsx
```

Expected: all page tests pass after adapting the existing single-layer mock assertions to `county-layer`.

- [ ] **Step 8: Commit immediate mode and county coloring**

```powershell
git add -- frontend/src/pages/IrrigationPage.tsx frontend/src/test/App.test.tsx
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: restore irrigation county statistics mode"
```

---

### Task 5: Implement Township Detail Switching Without Removing Counties

**Files:**
- Modify: `frontend/src/pages/IrrigationPage.tsx:115-600`
- Modify: `frontend/src/test/App.test.tsx:180-350`

**Interfaces:**
- Uses: Task 3 detail overlay props.
- Uses: Task 2 `LegendGroup` behavior.
- Produces state: `townshipVector`, `townshipAverages`, `townshipLegend`, `townshipLegendStatus`, `townshipCounty`, `pendingTownshipCounty`.
- Produces race guard: `townshipRequestIdRef: MutableRefObject<number>`.

Before the tests, add the shared fixture builder:

```tsx
function vectorFixture(
  level: 'county' | 'township',
  countyId?: string,
): IrrigationVectorGeoJSON {
  const isCountyB = countyId === 'county_b'
  const id = level === 'county' ? 'county_a' : isCountyB ? 'township_b1' : 'township_a1'
  const name = level === 'county' ? '示范县A' : isCountyB ? '示范镇B1' : '示范镇A1'
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: {
        id,
        name,
        ...(level === 'township' ? { parentId: countyId ?? 'county_a' } : {}),
      },
      geometry: {
        type: 'Polygon',
        coordinates: [[[100, 30], [101, 30], [101, 31], [100, 30]]],
      },
    }],
  }
}
```

- [ ] **Step 1: Strengthen the existing township test to require both layers**

After clicking “乡镇级统计”, assert:

```tsx
expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
expect(screen.getByTestId('township-layer')).toHaveTextContent('empty')
expect(apiMocks.getIrrigationRegionAverages).toHaveBeenCalledWith('county')
```

After clicking county A and waiting for its chunk:

```tsx
expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
expect(screen.getByTestId('township-layer')).toHaveTextContent('loaded')
expect(screen.getByRole('heading', { name: '县级年平均' })).toBeInTheDocument()
expect(screen.getByRole('heading', { name: '当前县乡镇年平均' })).toBeInTheDocument()
```

- [ ] **Step 2: Add a failing cross-county preservation test**

Update the vector mock so township features depend on `countyId`. Then add:

```tsx
it('keeps counties visible while switching the township detail to another county', async () => {
  window.history.pushState({}, '', '/irrigation')
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
  await user.click(await screen.findByRole('button', { name: '选择示范县A' }))
  await screen.findByText('已加载示范县A 1 个乡镇')

  await user.click(screen.getByRole('button', { name: '选择示范县B' }))
  expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
  expect(screen.getByTestId('township-layer')).toHaveTextContent('loaded')

  await waitFor(() => {
    expect(apiMocks.getIrrigationVectorGeoJSON).toHaveBeenCalledWith('township', 'county_b')
  })
  expect(await screen.findByText('已加载示范县B 1 个乡镇')).toBeInTheDocument()
  expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
})
```

- [ ] **Step 3: Add a failing stale-response test**

Expose `detail-first-id` from the MapView mock, then add:

```tsx
it('ignores a stale township response after a newer county finishes first', async () => {
  window.history.pushState({}, '', '/irrigation')
  const countyAChunk = deferred<IrrigationVectorGeoJSON>()
  const countyBChunk = deferred<IrrigationVectorGeoJSON>()
  apiMocks.getIrrigationVectorGeoJSON.mockImplementation(
    (level: 'county' | 'township', countyId?: string) => {
      if (level === 'township' && countyId === 'county_a') return countyAChunk.promise
      if (level === 'township' && countyId === 'county_b') return countyBChunk.promise
      return Promise.resolve(vectorFixture(level, countyId))
    },
  )
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
  await screen.findByText('请在地图上点击一个县域')
  await user.click(screen.getByRole('button', { name: '选择示范县A' }))
  await user.click(screen.getByRole('button', { name: '选择示范县B' }))

  countyBChunk.resolve(vectorFixture('township', 'county_b'))
  expect(await screen.findByText('已加载示范县B 1 个乡镇')).toBeInTheDocument()

  countyAChunk.resolve(vectorFixture('township', 'county_a'))
  await waitFor(() => {
    expect(screen.getByTestId('detail-first-id')).toHaveTextContent('township_b1')
  })
  expect(screen.queryByText(/已加载示范县A/)).not.toBeInTheDocument()
})
```

- [ ] **Step 4: Add a failing switch-error preservation test**

Configure the vector mock to reject only county B, load county A successfully, then click B:

```tsx
it('keeps the previous township layer when a new county chunk fails', async () => {
  window.history.pushState({}, '', '/irrigation')
  apiMocks.getIrrigationVectorGeoJSON.mockImplementation(
    (level: 'county' | 'township', countyId?: string) => {
      if (level === 'township' && countyId === 'county_b') {
        return Promise.reject(new Error('县B分片不可用'))
      }
      return Promise.resolve(vectorFixture(level, countyId))
    },
  )
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
  await user.click(await screen.findByRole('button', { name: '选择示范县A' }))
  await screen.findByText('已加载示范县A 1 个乡镇')
  await user.click(screen.getByRole('button', { name: '选择示范县B' }))

  expect(await screen.findByText('县B分片不可用')).toBeInTheDocument()
  expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
  expect(screen.getByTestId('detail-first-id')).toHaveTextContent('township_a1')
})
```

Define `vectorFixture(level, countyId)` once near the existing irrigation fixtures so all township tests use identical GeoJSON construction.

- [ ] **Step 5: Run the township tests and verify RED**

```powershell
npx vitest run src/test/App.test.tsx -t "loads townships only|keeps counties visible|ignores a stale township|keeps the previous township"
```

Expected: the current single `regionVector` replacement removes the county layer and has no cross-request guard.

- [ ] **Step 6: Implement isolated township detail state**

Add:

```tsx
const townshipRequestIdRef = useRef(0)
const [townshipVector, setTownshipVector] = useState<IrrigationVectorGeoJSON | null>(null)
const [townshipAverages, setTownshipAverages] = useState<IrrigationRegionAverage[]>([])
const [townshipLegend, setTownshipLegend] = useState<LegendItem[]>([])
const [townshipLegendStatus, setTownshipLegendStatus] = useState<LegendStatus>('loading')
const [townshipCounty, setTownshipCounty] = useState<{ id: string; name: string } | null>(null)
const [pendingTownshipCounty, setPendingTownshipCounty] = useState<{ id: string; name: string } | null>(null)
```

Derive the detail color map with the Task 4 helper:

```tsx
const townshipColorMap = useMemo(
  () => buildRegionColorMap(townshipAverages, townshipLegend),
  [townshipAverages, townshipLegend],
)
```

Replace the effect that clears `regionVector` with a callback using this sequence:

```tsx
const loadTownshipCounty = useCallback(async (county: { id: string; name: string }) => {
  const requestId = ++townshipRequestIdRef.current
  setPendingTownshipCounty(county)
  setSelectedRegion(null)
  setSeriesError('')
  try {
    const vector = await loadVector('township', county.id)
    if (requestId !== townshipRequestIdRef.current) return
    setTownshipVector(vector)
    setTownshipCounty(county)
    setTownshipAverages([])
    setTownshipLegend([])
    setTownshipLegendStatus('loading')
    setVectorStatus({
      level: 'township',
      available: true,
      url: `/api/irrigation/vectors/township?countyId=${encodeURIComponent(county.id)}`,
      message: `已加载${county.name} ${vector.features.length} 个乡镇`,
    })
    try {
      const averages = await getIrrigationRegionAverages('township', county.id)
      if (requestId !== townshipRequestIdRef.current) return
      setTownshipAverages(averages.averages)
      setTownshipLegend(averages.legend)
      setTownshipLegendStatus('ready')
    } catch {
      if (requestId === townshipRequestIdRef.current) setTownshipLegendStatus('error')
    }
  } catch (error) {
    if (requestId !== townshipRequestIdRef.current) return
    setVectorStatus({
      level: 'township',
      available: false,
      url: null,
      message: error instanceof Error ? error.message : '该县乡镇矢量暂不可用',
    })
  } finally {
    if (requestId === townshipRequestIdRef.current) setPendingTownshipCounty(null)
  }
}, [loadVector])
```

When leaving township mode, increment `townshipRequestIdRef.current` and clear only township detail state.

- [ ] **Step 7: Wire primary county and detail township callbacks**

Use county selection as follows:

```tsx
const handleCountySelect = useCallback((region: { id: string; name: string }) => {
  if (regionLevel === 'township') {
    void loadTownshipCounty(region)
    return
  }
  setSelectedRegion(region)
}, [loadTownshipCounty, regionLevel])
```

Pass to `MapView`:

```tsx
onRegionSelect={handleCountySelect}
selectedRegionId={regionLevel === 'county' ? selectedRegion?.id : townshipCounty?.id}
detailRegionVector={regionLevel === 'township' ? townshipVector : null}
detailRegionLevel={regionLevel === 'township' && townshipVector ? 'township' : null}
detailRegionColorMap={townshipColorMap}
detailSelectedRegionId={regionLevel === 'township' ? selectedRegion?.id : null}
onDetailRegionSelect={regionLevel === 'township' ? setSelectedRegion : undefined}
```

`returnToCountySelection` clears the six township states and invalidates the request ID; it must not clear `countyVector`, `countyAverages`, `countyLegend`, or `countyColorMap`.

- [ ] **Step 8: Pass two named Legend groups only after township detail is loaded**

Build:

```tsx
const adminLegendGroups = regionLevel === 'township' && townshipVector
  ? [
      { title: '县级年平均', items: countyLegend, status: countyLegendStatus },
      { title: '当前县乡镇年平均', items: townshipLegend, status: townshipLegendStatus },
    ]
  : [{ title: '县级年平均', items: countyLegend, status: countyLegendStatus }]
```

Pass `groups={isAdminStatsMode ? adminLegendGroups : undefined}` to `Legend`.

- [ ] **Step 9: Run page tests and verify GREEN**

```powershell
npx vitest run src/test/App.test.tsx
```

Expected: county and township layers coexist, B replaces only the detail layer, stale A cannot overwrite B, and existing series selection tests pass.

- [ ] **Step 10: Commit township detail behavior**

```powershell
git add -- frontend/src/pages/IrrigationPage.tsx frontend/src/test/App.test.tsx
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: retain counties during township drilldown"
```

---

### Task 6: Restore the Real County Catalog and Verify API Contracts

**Files:**
- Modify (generated): `data/stats/irrigation_regions.json`
- Modify: `backend/tests/test_irrigation.py:248-390`

**Interfaces:**
- Consumes: Task 1 `--regions-only` path.
- Verifies: `GET /api/irrigation/regions?level=county` and `GET /api/irrigation/regions/averages?level=county` return non-empty results.

- [ ] **Step 1: Add exact county/township catalog assertions**

Extend `backend/tests/test_irrigation.py`:

```python
def test_irrigation_region_catalog_contains_both_supported_levels():
    county = client.get("/api/irrigation/regions?level=county")
    township = client.get("/api/irrigation/regions?level=township")

    assert county.status_code == 200
    assert township.status_code == 200
    assert len(county.json()) > 0
    assert len(township.json()) > 0
    assert {item["level"] for item in county.json()} == {"county"}
    assert {item["level"] for item in township.json()} == {"township"}
```

Keep the existing test that a township averages request without `countyId` returns 422.

- [ ] **Step 2: Run the test and verify RED against the current corrupted catalog**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_irrigation.py -k "catalog_contains_both or regions_filters_by_level or region_averages_returns" -v -p no:cacheprovider
```

Expected before regeneration: county assertions fail because the current catalog has zero county entries.

- [ ] **Step 3: Regenerate only the catalog from the existing merged series**

```powershell
$env:PYTHONPATH='.'
python backend/precompute_irrigation.py --regions-only
```

Expected output: `Published 46619 regions` (the exact total may differ if the series file changes, but it must include approximately 2,893 counties plus 43,726 townships). The command must not read F: Shapefiles or recompute raster series.

- [ ] **Step 4: Verify the generated structure and API tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_precompute_irrigation.py backend/tests/test_irrigation.py -v -p no:cacheprovider
```

Expected: all tests in both files pass, including the two county tests that previously failed.

- [ ] **Step 5: Commit the restored catalog and API regression test**

```powershell
git add -- data/stats/irrigation_regions.json backend/tests/test_irrigation.py
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: restore irrigation county region metadata"
```

Review the staged data diff summary before committing; it must add county entries without removing township entries.

---

### Task 7: Run Complete Verification and Document Evidence

**Files:**
- Modify only if results require it: `progress.md`, `findings.md`, `task_plan.md`

**Interfaces:**
- Consumes all previous tasks.
- Produces final evidence for the six functional/performance acceptance criteria.

- [ ] **Step 1: Run focused backend tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_precompute_irrigation.py backend/tests/test_irrigation.py backend/tests/test_township_chunks.py -v -p no:cacheprovider
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the complete backend suite**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests -v -p no:cacheprovider
```

Expected: all tests pass; the previously known empty-county failures are resolved.

- [ ] **Step 3: Run focused and complete frontend tests**

From `frontend`:

```powershell
npx vitest run src/test/Legend.test.tsx src/test/MapView.test.tsx src/test/App.test.tsx src/test/api.test.ts
npx vitest run
```

Expected: all tests pass with no unhandled promise rejections.

- [ ] **Step 4: Run build and lint**

From `frontend`:

```powershell
npm run build
npm run lint
```

Expected: build succeeds; lint introduces no new warnings. Record the two known existing warnings separately if they remain.

- [ ] **Step 5: Recheck real chunk limits and API scope**

Run the existing chunk manifest verification or the focused chunk tests. Confirm:

```text
max chunk bytes < 1,000,000
max township features < 500
GET /api/irrigation/vectors/township without countyId -> 422
GET /api/irrigation/regions/averages?level=township without countyId -> 422
```

- [ ] **Step 6: Review the final diff**

```powershell
git status --short
git diff --check
git diff --stat
```

Expected: no whitespace errors; every changed file maps to a task above; unrelated user changes remain untouched.

- [ ] **Step 7: Record completion**

Update the active planning files with exact pass counts, catalog counts, maximum chunk size/features, build/lint result, and any environment-only limitation. Do not claim browser verification if the in-app browser still blocks localhost.

---

## Execution Notes

- Preserve vector-first loading: publish a township chunk to the map before awaiting its averages response, so a large statistics file cannot block geometry interaction.
- Do not clear `countyVector` when selecting, loading, failing, returning from, or switching a township county.
- Do not reuse county color thresholds for township values or vice versa; present both named groups when both layers are visible.
- If a target file has unrelated unstaged hunks, inspect the staged diff before every commit and omit the commit rather than mixing unrelated work without authorization.
