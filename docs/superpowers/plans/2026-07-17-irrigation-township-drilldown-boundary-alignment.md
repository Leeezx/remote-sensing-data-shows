# 灌溉乡镇下钻事件与县界对齐实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复县级统计切换到乡镇级统计后的陈旧点击回调，并把旧版乡镇要素在构建期对齐到当前县界，使嫩江市、孙吴县、牙克石市均能先加载乡镇矢量、再点击乡镇查询统计。

**Architecture:** `RegionOverlay` 通过 ref 把已绑定的 Leaflet click 委托给最新 React 回调，`IrrigationPage` 再以带行政级别的选择状态阻止县 ID 进入乡镇序列接口。分片构建器使用纯 Python 内部代表点、point-in-polygon 和一度网格 bbox 索引完成当前县归属，保留原乡镇 ID、写入当前县 `parentId`，通过审计、序列键校验和事务目录切换后发布。

**Tech Stack:** Python 3、FastAPI、pytest、React 19、TypeScript 6、React-Leaflet 5/Leaflet 1.9、Vitest、Testing Library、Vite、Oxlint。

## Global Constraints

- 乡镇分片固定输出到 `data/vectors/irrigation/township_by_county/{currentCountyCode}.geojson`。
- 单个分片最多 499 个要素且不超过 1,000,000 bytes；前后端现有保护不得弱化。
- 输出要素保留原始乡镇 `id`，设置 `level='township'`，并把 `parentId` 改为当前县九位 ID；统计序列继续以原乡镇 ID 查询。
- 不增加 Shapely、GeoPandas、PyGEOS 或其他几何依赖；空间归属只使用项目内纯 Python 几何函数。
- 不增加静态新旧县码别名表，不在 API 请求期间执行空间匹配，不强制 remount 全国 2,891 个县级 SVG path。
- 县点击只加载乡镇分片；只有来自乡镇详情层的点击才能请求 township monthly/annual 序列。
- 分片 404/空分片显示“该县暂无乡镇矢量”；乡镇序列 404 继续显示“暂无统计数据”。
- 构建遇到无匹配、多匹配、无效几何或序列键缺失时写审计文件并停止发布，旧正式目录保持完整；不得猜测归属。
- 当前工作区包含大量已有修改；每个任务只暂存列出的文件，提交前执行 `git diff --cached --name-only` 和 `git diff --cached --check`。
- `frontend/src/services/api.ts`、`frontend/src/test/api.test.ts` 和 `backend/tests/test_irrigation.py` 已有未提交改动，本计划不修改它们。

---

## File Structure

- `frontend/src/components/MapView.tsx`：让 `RegionOverlay` 的 Leaflet 事件调用最新选择回调。
- `frontend/src/test/MapView.test.tsx`：保存首次创建的旧 layer，rerender 后验证其 click 调用新回调。
- `frontend/src/pages/IrrigationPage.tsx`：为选择状态记录来源级别，区分分片错误与序列错误，拒绝空分片。
- `frontend/src/test/App.test.tsx`：覆盖县级→乡镇级切换、旧回调防线、县点击不查序列、乡镇点击查序列和分片 404/空响应。
- `backend/routers/irrigation.py`：返回带固定错误码的乡镇分片 404，并删除依赖旧代码前缀的未使用矢量查找入口。
- `backend/township_chunks.py`：保留运行时县码规范化和分片读取；移除不再成立且无调用者的乡镇前缀查找 helper。
- `backend/tests/test_township_vector_api.py`：隔离验证分片成功、缺失、损坏和超限响应，不触碰已有脏测试文件。
- `scripts/build_township_chunks.py`：新增几何原语、当前县空间索引、审计、序列校验、当前码分组和事务发布。
- `backend/tests/test_township_chunks.py`：覆盖几何、空间归属、新旧代码重映射、排除、清单、序列键和发布回滚。
- `data/vectors/irrigation/township_by_county/`：执行阶段用 `--force` 全量重建的本地分片目录；生成数据按现有忽略规则不加入代码提交。

---

### Task 1: Dispatch Leaflet Clicks Through the Latest React Callback

**Files:**
- Modify: `frontend/src/components/MapView.tsx:167-287`
- Modify: `frontend/src/test/MapView.test.tsx:454-481`

**Interfaces:**
- Preserves: `RegionOverlay.onRegionSelect?: (region: { id: string; name: string }) => void`.
- Produces: `onRegionSelectRef: MutableRefObject<typeof onRegionSelect>` updated on every render.
- Behavior consumed by Task 2: an existing county Leaflet layer invokes the current township-mode county handler after a React rerender.

- [ ] **Step 1: Write the failing stale-handler regression test**

Add beside the existing “latest county style” test in `frontend/src/test/MapView.test.tsx`:

```tsx
it('dispatches an existing county layer click through the latest callback', () => {
  const county = vectorFixture('county_a', '示范县A')
  const countyModeSelect = vi.fn()
  const townshipModeSelect = vi.fn()
  const { rerender } = render(
    <MapView
      {...baseProps}
      regionVector={county}
      regionLevel="county"
      onRegionSelect={countyModeSelect}
    />,
  )
  const mountedCountyLayer = mapMocks.featureLayers.find(
    (item) => item.id === 'county_a',
  )!

  rerender(
    <MapView
      {...baseProps}
      regionVector={county}
      regionLevel="county"
      onRegionSelect={townshipModeSelect}
    />,
  )

  act(() => {
    mountedCountyLayer.handlers.click?.({
      originalEvent: new MouseEvent('click'),
    })
  })

  expect(countyModeSelect).not.toHaveBeenCalled()
  expect(townshipModeSelect).toHaveBeenCalledWith({
    id: 'county_a',
    name: '示范县A',
  })
})
```

The test deliberately invokes the handler captured from the first mocked Leaflet layer rather than the new layer produced by the test double.

- [ ] **Step 2: Run the test and verify RED**

Run from `frontend`:

```powershell
npx vitest run src/test/MapView.test.tsx -t "dispatches an existing county layer click"
```

Expected: FAIL because `countyModeSelect` is called and `townshipModeSelect` is not called.

- [ ] **Step 3: Implement stable callback delegation**

In `RegionOverlay`, next to `styleInputsRef`, add and update the callback ref before the early return:

```tsx
const onRegionSelectRef = useRef(onRegionSelect)
onRegionSelectRef.current = onRegionSelect
```

Replace the final line of the Leaflet click handler:

```tsx
if (id) onRegionSelectRef.current?.({ id, name })
```

Keep the current GeoJSON `key`, pane order, style ref, hover behavior, tooltip batching, fitBounds behavior and 499-feature guard unchanged.

- [ ] **Step 4: Run focused and full MapView tests**

```powershell
npx vitest run src/test/MapView.test.tsx -t "dispatches an existing county layer click"
npx vitest run src/test/MapView.test.tsx
```

Expected: the new regression and all existing MapView tests pass.

- [ ] **Step 5: Commit the event freshness fix**

```powershell
git add -- frontend/src/components/MapView.tsx frontend/src/test/MapView.test.tsx
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: refresh irrigation region click handlers"
```

Expected staged files: exactly the two files listed above.

---

### Task 2: Enforce Two-Stage Selection and Separate Vector Errors

**Files:**
- Modify: `frontend/src/pages/IrrigationPage.tsx:68-520`
- Modify: `frontend/src/test/App.test.tsx:315-505`

**Interfaces:**
- Produces: `SelectedAdminRegion = { id: string; name: string; level: IrrigationRegionLevel }`.
- Produces: `isTownshipVectorNotFound(error: unknown) -> boolean` for the backend code introduced in Task 3.
- Produces: `handleTownshipSelect(region)` as the only path that writes a township selection.
- Consumes: Task 1 ensures a real existing county layer calls the current `handleCountySelect`.

- [ ] **Step 1: Add a failing defensive test for an old county-mode callback**

Add to `frontend/src/test/App.test.tsx`:

```tsx
it('never queries township series from a callback captured in county mode', async () => {
  window.history.pushState({}, '', '/irrigation')
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '县级统计' }))
  await waitFor(() => expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded'))
  const capturedCountyCallback = mapViewMocks.props?.onRegionSelect as
    | ((region: { id: string; name: string }) => void)
    | undefined

  await user.click(screen.getByRole('button', { name: '乡镇级统计' }))
  await act(async () => {
    capturedCountyCallback?.({ id: 'county_a', name: '示范县A' })
    await Promise.resolve()
  })

  expect(apiMocks.getIrrigationSeries).not.toHaveBeenCalledWith(
    'township',
    'county_a',
    expect.any(String),
  )
})
```

This page-level guard complements Task 1: even if another stale event path appears later, a county-origin selection cannot become a township-series request.

- [ ] **Step 2: Add the exact county→township→county→township request test**

```tsx
it('loads a township chunk after switching from county mode and queries only after a township click', async () => {
  window.history.pushState({}, '', '/irrigation')
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '县级统计' }))
  await waitFor(() => expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded'))
  await user.click(screen.getByRole('button', { name: '乡镇级统计' }))
  await user.click(screen.getByRole('button', { name: '选择示范县A' }))

  expect(await screen.findByText('已加载示范县A 1 个乡镇')).toBeInTheDocument()
  expect(apiMocks.getIrrigationVectorGeoJSON).toHaveBeenCalledWith(
    'township',
    'county_a',
  )
  expect(apiMocks.getIrrigationSeries).not.toHaveBeenCalledWith(
    'township',
    'county_a',
    expect.any(String),
  )

  await user.click(screen.getByRole('button', { name: '选择示范镇A1' }))
  await waitFor(() => {
    expect(apiMocks.getIrrigationSeries).toHaveBeenCalledWith(
      'township',
      'township_a1',
      'monthly',
    )
    expect(apiMocks.getIrrigationSeries).toHaveBeenCalledWith(
      'township',
      'township_a1',
      'annual',
    )
  })
})
```

- [ ] **Step 3: Add failing coded-404 and empty-chunk tests**

```tsx
it('shows a township-vector message for a missing county chunk', async () => {
  window.history.pushState({}, '', '/irrigation')
  apiMocks.getIrrigationVectorGeoJSON.mockImplementation(
    (level: 'county' | 'township', countyId?: string) => {
      if (level === 'township' && countyId === 'county_a') {
        return Promise.reject({
          response: {
            status: 404,
            data: {
              detail: {
                code: 'township_vector_not_found',
                message: '该县暂无乡镇矢量',
              },
            },
          },
        })
      }
      return Promise.resolve(vectorFixture(level, countyId))
    },
  )
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
  await user.click(screen.getByRole('button', { name: '选择示范县A' }))

  expect((await screen.findAllByText('该县暂无乡镇矢量')).length).toBeGreaterThan(0)
  expect(screen.queryByText('暂无统计数据')).not.toBeInTheDocument()
  expect(apiMocks.getIrrigationSeries).not.toHaveBeenCalled()
})

it('treats an empty county chunk as unavailable township geometry', async () => {
  window.history.pushState({}, '', '/irrigation')
  apiMocks.getIrrigationVectorGeoJSON.mockImplementation(
    (level: 'county' | 'township', countyId?: string) => Promise.resolve(
      level === 'township'
        ? { type: 'FeatureCollection', features: [] }
        : vectorFixture(level, countyId),
    ),
  )
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
  await user.click(screen.getByRole('button', { name: '选择示范县A' }))

  expect((await screen.findAllByText('该县暂无乡镇矢量')).length).toBeGreaterThan(0)
  expect(apiMocks.getIrrigationRegionAverages).not.toHaveBeenCalledWith(
    'township',
    'county_a',
  )
  expect(apiMocks.getIrrigationSeries).not.toHaveBeenCalled()
})
```

- [ ] **Step 4: Run the new page tests and verify RED**

```powershell
npx vitest run src/test/App.test.tsx -t "never queries township series|loads a township chunk after switching|missing county chunk|empty county chunk"
```

Expected: the captured old callback queries `township/county_a`; coded 404 shows a generic message; empty chunk is accepted as a successful load.

- [ ] **Step 5: Add selection provenance and the coded-error predicate**

Above `IrrigationPage`, add:

```tsx
type SelectedAdminRegion = {
  id: string
  name: string
  level: IrrigationRegionLevel
}

function isTownshipVectorNotFound(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const ownCode = 'code' in error ? (error as { code?: unknown }).code : null
  if (ownCode === 'township_vector_not_found') return true
  if (!('response' in error)) return false
  const response = (error as {
    response?: {
      status?: number
      data?: { detail?: { code?: string } }
    }
  }).response
  return response?.status === 404
    && response.data?.detail?.code === 'township_vector_not_found'
}
```

Change the selection state to:

```tsx
const [selectedRegion, setSelectedRegion] = useState<SelectedAdminRegion | null>(null)
```

Replace the series effect guard and calls with:

```tsx
if (!regionLevel || !selectedRegion || selectedRegion.level !== regionLevel) {
  if (selectedRegion && selectedRegion.level !== regionLevel) {
    setSelectedRegion(null)
  }
  setMonthlySeries(null)
  setAnnualSeries(null)
  return
}
let cancelled = false
setSeriesError('')
Promise.all([
  getIrrigationSeries(selectedRegion.level, selectedRegion.id, 'monthly'),
  getIrrigationSeries(selectedRegion.level, selectedRegion.id, 'annual'),
])
```

The existing success, 404 and cancellation branches remain unchanged.

- [ ] **Step 6: Make county and township handlers write explicit levels**

Replace `handleCountySelect` and add `handleTownshipSelect`:

```tsx
const handleCountySelect = useCallback((region: { id: string; name: string }) => {
  if (regionLevel === 'township') {
    void loadTownshipCounty(region)
    return
  }
  setSelectedRegion({ ...region, level: 'county' })
}, [loadTownshipCounty, regionLevel])

const handleTownshipSelect = useCallback((region: { id: string; name: string }) => {
  if (regionLevel !== 'township') return
  setSelectedRegion({ ...region, level: 'township' })
}, [regionLevel])
```

Pass the new handler:

```tsx
onDetailRegionSelect={regionLevel === 'township' ? handleTownshipSelect : undefined}
```

- [ ] **Step 7: Reject missing and empty township vectors without touching series state**

Immediately after `loadVector('township', county.id)` returns, add:

```tsx
if (vector.features.length === 0) {
  throw Object.assign(new Error('该县暂无乡镇矢量'), {
    code: 'township_vector_not_found',
  })
}
```

In the outer catch of `loadTownshipCounty`, calculate the message before `setVectorStatus`:

```tsx
const message = isTownshipVectorNotFound(error)
  ? '该县暂无乡镇矢量'
  : error instanceof Error
    ? error.message
    : '该县乡镇矢量暂不可用'
```

Use `message` in `vectorStatus`. Do not clear `townshipVector` or `townshipCounty` in this failure branch; the existing last successful detail layer remains visible.

- [ ] **Step 8: Run focused and full page tests**

```powershell
npx vitest run src/test/App.test.tsx -t "never queries township series|loads a township chunk after switching|missing county chunk|empty county chunk"
npx vitest run src/test/App.test.tsx
```

Expected: all new and existing page tests pass, including stale response and failed cross-county preservation tests.

- [ ] **Step 9: Commit the page-state fix**

```powershell
git add -- frontend/src/pages/IrrigationPage.tsx frontend/src/test/App.test.tsx
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: separate township vectors from series selection"
```

Expected staged files: exactly the two files listed above.

---

### Task 3: Return a Coded Township-Vector 404 and Remove the Obsolete Prefix Lookup

**Files:**
- Modify: `backend/routers/irrigation.py:18-69,166-203`
- Modify: `backend/township_chunks.py:1-52`
- Create: `backend/tests/test_township_vector_api.py`

**Interfaces:**
- Produces 404 detail: `{ "code": "township_vector_not_found", "message": "该县暂无乡镇矢量", "countyId": string }`.
- Preserves: `county_code_from_id`, `county_id_from_code`, `township_parent_code`, `township_chunk_path`, `load_township_chunk`.
- Removes: unused `find_irrigation_vector_feature` and `find_township_feature`, whose prefix lookup is invalid after spatial remapping.

- [ ] **Step 1: Write isolated API contract tests**

Create `backend/tests/test_township_vector_api.py`:

```python
import json

from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import irrigation as irrigation_router


client = TestClient(app)


def test_township_vector_returns_coded_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "township_vector_not_found",
        "message": "该县暂无乡镇矢量",
        "countyId": "156231183",
    }


def test_township_vector_keeps_corruption_distinct_from_absence(
    monkeypatch,
    tmp_path,
):
    (tmp_path / "231183.geojson").write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Township vector chunk is unreadable"


def test_township_vector_serves_current_county_code(monkeypatch, tmp_path):
    chunk = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "id": "231121100001",
                "name": "测试乡镇",
                "level": "township",
                "parentId": "156231183",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[125, 49], [126, 49], [126, 50], [125, 49]]],
            },
        }],
    }
    (tmp_path / "231183.geojson").write_text(
        json.dumps(chunk, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 200
    assert response.json() == chunk
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert response.headers["etag"]


def test_township_vector_rejects_a_chunk_above_the_byte_limit(
    monkeypatch,
    tmp_path,
):
    (tmp_path / "231183.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)
    monkeypatch.setattr(irrigation_router, "MAX_TOWNSHIP_CHUNK_BYTES", 10)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Township vector chunk exceeds the configured delivery limits"
    )
```

- [ ] **Step 2: Run the API tests and verify RED**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_vector_api.py -v -p no:cacheprovider
```

Expected: the not-found assertion fails because the current route returns a plain English string.

- [ ] **Step 3: Return the fixed not-found detail**

In `township_vector_geojson`, replace the missing-file exception with:

```python
if not chunk_path.is_file():
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "township_vector_not_found",
            "message": "该县暂无乡镇矢量",
            "countyId": countyId,
        },
    )
```

Keep invalid IDs at 422, unreadable chunks at 500, over-limit chunks at 503, and successful `FileResponse` cache headers unchanged.

- [ ] **Step 4: Delete the no-longer-valid unused lookup path**

From `backend/routers/irrigation.py`, remove `find_township_feature` from the import and delete the entire `find_irrigation_vector_feature` function.

From `backend/township_chunks.py`, delete:

```python
def find_township_feature(root: Path, township_id: str) -> dict | None:
    try:
        data = load_township_chunk(root, township_parent_code(township_id))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        if str(properties.get("id", "")) == township_id:
            return feature
    return None
```

Keep `township_parent_code` because Task 4 uses the original prefix only as a spatially verified direct-match hint.

- [ ] **Step 5: Run API and helper tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_vector_api.py backend/tests/test_township_chunks.py -v -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 6: Commit the backend contract**

```powershell
git add -- backend/routers/irrigation.py backend/township_chunks.py backend/tests/test_township_vector_api.py
git diff --cached --name-only
git diff --cached --check
git commit -m "fix: distinguish missing township vector chunks"
```

Expected staged files: exactly the three files listed above. Inspect the full staged content of the previously untracked `backend/township_chunks.py` before committing.

---

### Task 4: Add Pure-Python Geometry and Current-County Spatial Indexing

**Files:**
- Modify: `scripts/build_township_chunks.py:14-165`
- Modify: `backend/tests/test_township_chunks.py`

**Interfaces:**
- Produces: `geometry_rings(geometry: dict) -> list[list[list[float]]]`.
- Produces: `point_in_geometry(point: tuple[float, float], geometry: dict) -> bool`.
- Produces: `representative_point(geometry: dict) -> tuple[float, float]`.
- Produces: immutable `CountyBoundary(code, county_id, name, geometry, bbox)`.
- Produces: `CountySpatialIndex.from_features(features)` and `.match(feature) -> tuple[CountyBoundary, str]`, where mode is `direct` or `spatial`.
- Raises: `TownshipAlignmentError` with reason `invalid_geometry`, `unmatched` or `ambiguous` and JSON-ready audit fields.

- [ ] **Step 1: Write failing geometry tests**

Extend `backend/tests/test_township_chunks.py` imports with `pytest` and the new builder symbols, then add:

```python
import pytest

from scripts.build_township_chunks import (
    CountySpatialIndex,
    TownshipAlignmentError,
    point_in_geometry,
    representative_point,
    simplify_ring,
)


def polygon(rings):
    return {"type": "Polygon", "coordinates": rings}


def feature(region_id, name, geometry):
    return {
        "type": "Feature",
        "properties": {"id": region_id, "name": name},
        "geometry": geometry,
    }


def test_point_in_geometry_respects_a_hole():
    geometry = polygon([
        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
        [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
    ])

    assert point_in_geometry((2, 2), geometry) is True
    assert point_in_geometry((5, 5), geometry) is False


def test_representative_point_stays_inside_a_concave_polygon_with_a_hole():
    geometry = polygon([
        [[0, 0], [8, 0], [8, 2], [2, 2], [2, 8], [0, 8], [0, 0]],
        [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]],
    ])

    point = representative_point(geometry)

    assert point_in_geometry(point, geometry) is True


def test_representative_point_handles_multipolygon_parts():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            [[[10, 10], [14, 10], [14, 14], [10, 10]]],
        ],
    }

    point = representative_point(geometry)

    assert point_in_geometry(point, geometry) is True
```

- [ ] **Step 2: Write failing current-county matching tests**

```python
def test_county_index_reports_direct_and_spatial_matches():
    counties = [
        feature(
            "156231183",
            "嫩江市",
            polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
        ),
        feature(
            "156231124",
            "孙吴县",
            polygon([[[130, 45], [140, 45], [140, 55], [130, 55], [130, 45]]]),
        ),
    ]
    index = CountySpatialIndex.from_features(counties)

    direct, direct_mode = index.match(feature(
        "231124100001",
        "直接匹配镇",
        polygon([[[131, 46], [132, 46], [132, 47], [131, 46]]]),
    ))
    remapped, remapped_mode = index.match(feature(
        "231121100001",
        "旧嫩江县乡镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    ))

    assert (direct.code, direct_mode) == ("231124", "direct")
    assert (remapped.code, remapped_mode) == ("231183", "spatial")


def test_county_index_fails_for_unmatched_or_multiple_counties():
    duplicate_geometry = polygon([
        [[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]],
    ])
    index = CountySpatialIndex.from_features([
        feature("156231183", "嫩江市", duplicate_geometry),
        feature("156999999", "重叠测试县", duplicate_geometry),
    ])

    with pytest.raises(TownshipAlignmentError, match="ambiguous"):
        index.match(feature(
            "231121100001",
            "歧义镇",
            polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
        ))

    empty_index = CountySpatialIndex.from_features([])
    with pytest.raises(TownshipAlignmentError, match="unmatched"):
        empty_index.match(feature(
            "231121100002",
            "无匹配镇",
            polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
        ))

    with pytest.raises(TownshipAlignmentError, match="invalid_geometry"):
        index.match({
            "type": "Feature",
            "properties": {"id": "231121100003", "name": "坏几何镇"},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        })
```

- [ ] **Step 3: Run the geometry tests and verify RED**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_chunks.py -k "point_in or representative or county_index" -v -p no:cacheprovider
```

Expected: collection fails because the geometry/index symbols do not exist.

- [ ] **Step 4: Implement ring extraction, parity containment and an interior scanline point**

Add to `scripts/build_township_chunks.py` before simplification helpers:

```python
from dataclasses import dataclass


Point = tuple[float, float]
Ring = list[list[float]]


def geometry_rings(geometry: dict) -> list[Ring]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        rings = list(coordinates)
    elif geometry_type == "MultiPolygon":
        rings = [ring for polygon in coordinates for ring in polygon]
    else:
        raise ValueError(f"Unsupported polygon geometry: {geometry_type}")
    valid = [ring for ring in rings if len(ring) >= 4]
    if not valid:
        raise ValueError("Polygon geometry has no valid rings")
    return valid


def _point_on_segment(point: Point, start: list[float], end: list[float]) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > 1e-10:
        return False
    return (
        min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10
        and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10
    )


def _point_in_ring(point: Point, ring: Ring) -> bool:
    x, y = point
    inside = False
    for start, end in zip(ring, ring[1:] + ring[:1]):
        if _point_on_segment(point, start, end):
            return True
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if crossing_x > x:
                inside = not inside
    return inside


def point_in_geometry(point: Point, geometry: dict) -> bool:
    inside = False
    for ring in geometry_rings(geometry):
        if _point_in_ring(point, ring):
            inside = not inside
    return inside


def _signed_ring_area(ring: Ring) -> float:
    return 0.5 * sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(ring, ring[1:] + ring[:1])
    )


def _ring_centroid(ring: Ring) -> Point | None:
    cross_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    for start, end in zip(ring, ring[1:] + ring[:1]):
        cross = start[0] * end[1] - end[0] * start[1]
        cross_sum += cross
        x_sum += (start[0] + end[0]) * cross
        y_sum += (start[1] + end[1]) * cross
    if abs(cross_sum) < 1e-12:
        return None
    return (x_sum / (3 * cross_sum), y_sum / (3 * cross_sum))


def _scanline_intersections(y: float, rings: list[Ring]) -> list[float]:
    intersections: list[float] = []
    for ring in rings:
        for start, end in zip(ring, ring[1:] + ring[:1]):
            x1, y1 = start
            x2, y2 = end
            if (y1 <= y < y2) or (y2 <= y < y1):
                intersections.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    return sorted(intersections)


def representative_point(geometry: dict) -> Point:
    rings = geometry_rings(geometry)
    largest_ring = max(rings, key=lambda ring: abs(_signed_ring_area(ring)))
    centroid = _ring_centroid(largest_ring)
    if centroid is not None and point_in_geometry(centroid, geometry):
        return centroid
    y_values = sorted({point[1] for ring in rings for point in ring})
    if len(y_values) < 2:
        raise ValueError("Polygon geometry has no interior")
    middle_y = (y_values[0] + y_values[-1]) / 2
    scanlines = sorted(
        ((start + end) / 2 for start, end in zip(y_values, y_values[1:])),
        key=lambda value: abs(value - middle_y),
    )
    for y in scanlines:
        xs = _scanline_intersections(y, rings)
        intervals = sorted(
            zip(xs[0::2], xs[1::2]),
            key=lambda pair: pair[1] - pair[0],
            reverse=True,
        )
        for start_x, end_x in intervals:
            candidate = ((start_x + end_x) / 2, y)
            if point_in_geometry(candidate, geometry):
                return candidate
    raise ValueError("Polygon geometry has no valid interior point")
```

- [ ] **Step 5: Implement the one-degree bbox index and auditable match error**

```python
@dataclass(frozen=True)
class CountyBoundary:
    code: str
    county_id: str
    name: str
    geometry: dict
    bbox: tuple[float, float, float, float]


class TownshipAlignmentError(ValueError):
    def __init__(
        self,
        reason: str,
        township_id: str,
        name: str,
        point: Point | None,
        candidates: list[str],
    ):
        super().__init__(f"{reason}: {township_id} {name}")
        self.reason = reason
        self.township_id = township_id
        self.name = name
        self.point = point
        self.candidates = candidates

    def as_dict(self) -> dict:
        return {
            "reason": self.reason,
            "townshipId": self.township_id,
            "name": self.name,
            "point": list(self.point) if self.point is not None else None,
            "candidateCountyCodes": self.candidates,
        }


def _geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    points = [point for ring in geometry_rings(geometry) for point in ring]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


class CountySpatialIndex:
    GRID_SIZE = 1.0

    def __init__(self, counties: list[CountyBoundary]):
        self.by_code = {county.code: county for county in counties}
        self.cells: dict[tuple[int, int], list[CountyBoundary]] = {}
        for county in counties:
            min_x, min_y, max_x, max_y = county.bbox
            for cell_x in range(math.floor(min_x), math.floor(max_x) + 1):
                for cell_y in range(math.floor(min_y), math.floor(max_y) + 1):
                    self.cells.setdefault((cell_x, cell_y), []).append(county)

    @classmethod
    def from_features(cls, features) -> "CountySpatialIndex":
        counties = []
        for feature in features:
            properties = feature.get("properties", {})
            county_id = str(properties.get("id", ""))
            code = county_code_from_id(county_id)
            geometry = feature.get("geometry", {})
            counties.append(CountyBoundary(
                code=code,
                county_id=county_id_from_code(code),
                name=str(properties.get("name", county_id)),
                geometry=geometry,
                bbox=_geometry_bbox(geometry),
            ))
        return cls(counties)

    def _candidates(self, point: Point) -> list[CountyBoundary]:
        x, y = point
        candidates = self.cells.get((math.floor(x), math.floor(y)), [])
        unique = {county.code: county for county in candidates}
        return [
            county
            for county in unique.values()
            if county.bbox[0] <= x <= county.bbox[2]
            and county.bbox[1] <= y <= county.bbox[3]
        ]

    def match(self, feature: dict) -> tuple[CountyBoundary, str]:
        properties = feature.get("properties", {})
        township_id = str(properties.get("id", ""))
        name = str(properties.get("name", township_id))
        try:
            point = representative_point(feature.get("geometry", {}))
        except ValueError as exc:
            raise TownshipAlignmentError(
                "invalid_geometry", township_id, name, None, [],
            ) from exc
        matches = [
            county
            for county in self._candidates(point)
            if point_in_geometry(point, county.geometry)
        ]
        if len(matches) == 0:
            raise TownshipAlignmentError("unmatched", township_id, name, point, [])
        if len(matches) > 1:
            raise TownshipAlignmentError(
                "ambiguous",
                township_id,
                name,
                point,
                sorted(county.code for county in matches),
            )
        county = matches[0]
        mode = "direct" if township_parent_code(township_id) == county.code else "spatial"
        return county, mode
```

Add `county_code_from_id` to the existing import from `backend.township_chunks`.

- [ ] **Step 6: Run geometry/index and full chunk-helper tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_chunks.py -k "point_in or representative or county_index" -v -p no:cacheprovider
python -m pytest backend/tests/test_township_chunks.py -v -p no:cacheprovider
```

Expected: all geometry, index and existing simplification/code tests pass.

- [ ] **Step 7: Commit the geometry/index layer**

```powershell
git add -- scripts/build_township_chunks.py backend/tests/test_township_chunks.py
git diff --cached --name-only
git diff --cached --check
git commit -m "feat: align township geometry to current counties"
```

Expected staged files: exactly the two files listed above. Because both were previously untracked, inspect their complete staged contents.

---

### Task 5: Build Current-Code Chunks with Audit, Series Validation, and Transactional Publication

**Files:**
- Modify: `scripts/build_township_chunks.py:166-300`
- Modify: `backend/tests/test_township_chunks.py`

**Interfaces:**
- Changes: `build_chunks(source, county_source, series_path, output, tolerance, max_bytes, max_features, force, exclusions=None) -> dict`.
- Produces successful manifest keys: `countySource`, `countySourceMtime`, `countyFeatureCount`, `seriesSource`, `townshipIdCount`, and `alignment` counts.
- Produces failure audit: sibling `<output-name>.alignment-audit.json`; failure never changes the existing output directory.
- Produces output features with `{ id, name, level: 'township', parentId: currentCountyId }`.

- [ ] **Step 1: Write the old-code→current-code integration test**

Add to `backend/tests/test_township_chunks.py`:

```python
import json
from pathlib import Path

import scripts.build_township_chunks as builder


def test_build_chunks_publishes_old_township_under_current_county(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "township_by_county"
    township_source.touch()
    county_source.touch()
    series_path.write_text(json.dumps({
        "township": {"231121100001": {"monthly": [], "annual": []}},
    }), encoding="utf-8")

    county_feature = feature(
        "156231183",
        "嫩江市",
        polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
    )
    township_feature = feature(
        "231121100001",
        "旧嫩江县乡镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )

    def fake_features(path):
        return iter([county_feature] if path == county_source else [township_feature])

    monkeypatch.setattr(builder, "iter_shapefile_geojson_features", fake_features)

    manifest = builder.build_chunks(
        township_source,
        county_source,
        series_path,
        output,
        tolerance=0,
        max_bytes=1_000_000,
        max_features=499,
        force=False,
    )

    assert not (output / "231121.geojson").exists()
    chunk = json.loads((output / "231183.geojson").read_text(encoding="utf-8"))
    assert chunk["features"][0]["properties"] == {
        "id": "231121100001",
        "name": "旧嫩江县乡镇",
        "level": "township",
        "parentId": "156231183",
    }
    assert manifest["alignment"] == {
        "direct": 0,
        "spatial": 1,
        "excluded": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "invalidGeometry": 0,
        "missingSeries": 0,
    }
```

- [ ] **Step 2: Write failing audit, exclusion, series and rollback tests**

```python
def test_build_chunks_audits_unmatched_and_preserves_existing_output(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "township_by_county"
    township_source.touch()
    county_source.touch()
    series_path.write_text(json.dumps({
        "township": {"231121100001": {}},
    }), encoding="utf-8")
    output.mkdir()
    (output / "sentinel.geojson").write_text("old", encoding="utf-8")

    township = feature(
        "231121100001",
        "无匹配镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )
    monkeypatch.setattr(
        builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([] if path == county_source else [township]),
    )

    with pytest.raises(ValueError, match="alignment audit"):
        builder.build_chunks(
            township_source,
            county_source,
            series_path,
            output,
            0,
            1_000_000,
            499,
            force=True,
        )

    assert (output / "sentinel.geojson").read_text(encoding="utf-8") == "old"
    audit = json.loads(
        (tmp_path / "township_by_county.alignment-audit.json").read_text(
            encoding="utf-8",
        ),
    )
    assert audit["issues"][0]["reason"] == "unmatched"


def test_build_chunks_requires_every_output_id_in_township_series(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "out"
    township_source.touch()
    county_source.touch()
    series_path.write_text('{"township": {}}', encoding="utf-8")
    county = feature(
        "156231183",
        "嫩江市",
        polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
    )
    township = feature(
        "231121100001",
        "缺序列镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )
    monkeypatch.setattr(
        builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([county] if path == county_source else [township]),
    )

    with pytest.raises(ValueError, match="missing township series"):
        builder.build_chunks(
            township_source,
            county_source,
            series_path,
            output,
            0,
            1_000_000,
            499,
            force=False,
        )

    assert not output.exists()


def test_explicit_exclusion_requires_a_nonempty_reason(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="non-empty reason"):
        builder.validate_exclusions({"231121100001": ""})

    assert builder.validate_exclusions({
        "231121100001": "source does not cover this jurisdiction",
    }) == {
        "231121100001": "source does not cover this jurisdiction",
    }


def test_build_chunks_records_a_reviewed_exclusion(monkeypatch, tmp_path):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "out"
    township_source.touch()
    county_source.touch()
    series_path.write_text('{"township": {}}', encoding="utf-8")
    excluded = feature(
        "231121100001",
        "明确排除镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )
    monkeypatch.setattr(
        builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([] if path == county_source else [excluded]),
    )

    manifest = builder.build_chunks(
        township_source,
        county_source,
        series_path,
        output,
        0,
        1_000_000,
        499,
        force=False,
        exclusions={"231121100001": "unsupported source jurisdiction"},
    )

    assert manifest["alignment"]["excluded"] == 1
    assert manifest["excludedTownships"] == {
        "231121100001": "unsupported source jurisdiction",
    }
    assert manifest["featureCount"] == 0


def test_fit_chunk_rejects_payload_that_cannot_meet_the_byte_limit():
    oversized_feature = feature(
        "231121100001",
        "字节上限测试镇",
        polygon([[[0, 0], [10, 0], [10, 10], [0, 0]]]),
    )

    with pytest.raises(ValueError, match="limit is 20"):
        builder._fit_chunk_to_limit([oversized_feature], 0, 20)


def test_build_chunks_rejects_a_county_above_the_feature_limit(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "out"
    township_source.touch()
    county_source.touch()
    ids = ["231121100001", "231121100002"]
    series_path.write_text(json.dumps({
        "township": {region_id: {} for region_id in ids},
    }), encoding="utf-8")
    county = feature(
        "156231183",
        "嫩江市",
        polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
    )
    townships = [
        feature(
            region_id,
            f"测试镇{index}",
            polygon([[
                [125 + index, 49],
                [125.4 + index, 49],
                [125 + index, 49.4],
                [125 + index, 49],
            ]]),
        )
        for index, region_id in enumerate(ids)
    ]
    monkeypatch.setattr(
        builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([county] if path == county_source else townships),
    )

    with pytest.raises(ValueError, match="limit is 1"):
        builder.build_chunks(
            township_source,
            county_source,
            series_path,
            output,
            0,
            1_000_000,
            1,
            force=False,
        )

    assert not output.exists()


def test_publish_staged_directory_restores_old_output_when_swap_fails(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "township_by_county"
    staged = tmp_path / "staged"
    output.mkdir()
    staged.mkdir()
    (output / "old.geojson").write_text("old", encoding="utf-8")
    (staged / "new.geojson").write_text("new", encoding="utf-8")
    real_replace = Path.replace

    def failing_replace(path, target):
        if path == staged:
            raise OSError("simulated staged swap failure")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated staged swap failure"):
        builder._publish_staged_directory(staged, output)

    assert (output / "old.geojson").read_text(encoding="utf-8") == "old"
    assert not (output / "new.geojson").exists()
```

- [ ] **Step 3: Run integration tests and verify RED**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_chunks.py -k "build_chunks or exclusion" -v -p no:cacheprovider
```

Expected: `build_chunks` rejects the new signature and lacks alignment/audit behavior.

- [ ] **Step 4: Add input validation, county index construction and series-key loading**

Add:

```python
def validate_exclusions(exclusions: dict[str, str] | None) -> dict[str, str]:
    result = {}
    for township_id, reason in (exclusions or {}).items():
        normalized_reason = str(reason).strip()
        township_parent_code(str(township_id))
        if not normalized_reason:
            raise ValueError("Every excluded township id needs a non-empty reason")
        result[str(township_id)] = normalized_reason
    return result


def _township_series_ids(series_path: Path) -> set[str]:
    payload = json.loads(series_path.read_text(encoding="utf-8"))
    township = payload.get("township", {})
    if not isinstance(township, dict):
        raise ValueError("Series JSON must contain a township object")
    return {str(region_id) for region_id in township}


def _audit_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.alignment-audit.json")
```

At the start of `build_chunks`, replace the old manifest-only output guard with the following validation, then build the index once:

```python
if output.exists() and not force:
    raise FileExistsError(f"Output already exists; pass --force to rebuild: {output}")
county_features = list(iter_shapefile_geojson_features(county_source))
county_index = CountySpatialIndex.from_features(county_features)
series_ids = _township_series_ids(series_path)
excluded = validate_exclusions(exclusions)
```

- [ ] **Step 5: Replace prefix-only grouping with audited spatial grouping**

Inside the township feature loop use:

```python
alignment_counts = {
    "direct": 0,
    "spatial": 0,
    "excluded": 0,
    "unmatched": 0,
    "ambiguous": 0,
    "invalidGeometry": 0,
    "missingSeries": 0,
}
issues = []
assigned_counties: dict[str, str] = {}
output_township_ids: set[str] = set()

for feature in iter_shapefile_geojson_features(source):
    properties = feature.get("properties", {})
    township_id = str(properties.get("id", ""))
    name = str(properties.get("name", township_id))
    if township_id in excluded:
        alignment_counts["excluded"] += 1
        continue
    try:
        county, mode = county_index.match(feature)
        previous_code = assigned_counties.get(township_id)
        if previous_code is not None and previous_code != county.code:
            raise TownshipAlignmentError(
                "ambiguous",
                township_id,
                name,
                representative_point(feature["geometry"]),
                sorted({previous_code, county.code}),
            )
    except TownshipAlignmentError as exc:
        issues.append(exc.as_dict())
        count_key = "invalidGeometry" if exc.reason == "invalid_geometry" else exc.reason
        alignment_counts[count_key] += 1
        continue
    assigned_counties[township_id] = county.code
    alignment_counts[mode] += 1
    output_township_ids.add(township_id)
    compact_feature = {
        "type": "Feature",
        "properties": {
            "id": township_id,
            "name": name,
            "level": "township",
            "parentId": county.county_id,
        },
        "geometry": simplify_geometry(feature["geometry"], tolerance),
    }
    pool.write(
        records_root / f"{county.code}.ndjson",
        json.dumps(compact_feature, ensure_ascii=False, separators=(",", ":")),
    )
    counts[county.code] = counts.get(county.code, 0) + 1
```

After closing the pool, add missing-series issues and stop before writing or publishing chunks:

```python
for township_id in sorted(output_township_ids - series_ids):
    alignment_counts["missingSeries"] += 1
    issues.append({
        "reason": "missing_series",
        "townshipId": township_id,
        "name": township_id,
        "point": None,
        "candidateCountyCodes": [assigned_counties[township_id]],
    })

if issues:
    audit = {
        "status": "failed",
        "source": str(source),
        "countySource": str(county_source),
        "seriesSource": str(series_path),
        "alignment": alignment_counts,
        "issues": issues,
    }
    _audit_path(output).write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if alignment_counts["missingSeries"]:
        raise ValueError("Build blocked by missing township series; see alignment audit")
    raise ValueError("Build blocked by alignment audit")
```

- [ ] **Step 6: Extend the successful manifest**

Keep all existing per-chunk and maximum fields, and add:

```python
manifest = {
    "source": str(source),
    "sourceMtime": source.stat().st_mtime,
    "countySource": str(county_source),
    "countySourceMtime": county_source.stat().st_mtime,
    "countyFeatureCount": len(county_features),
    "seriesSource": str(series_path),
    "chunkCount": len(manifest_chunks),
    "featureCount": sum(counts.values()),
    "townshipIdCount": len(output_township_ids),
    "alignment": alignment_counts,
    "excludedTownships": excluded,
    "maxChunkBytes": max(
        (item["bytes"] for item in manifest_chunks.values()),
        default=0,
    ),
    "maxChunkFeatures": max(
        (item["featureCount"] for item in manifest_chunks.values()),
        default=0,
    ),
    "elapsedSeconds": round(time.perf_counter() - started, 3),
    "chunks": manifest_chunks,
}
```

Do not publish if any alignment count for `unmatched`, `ambiguous`, `invalidGeometry` or `missingSeries` is nonzero.

- [ ] **Step 7: Replace per-file overwrite with transactional directory publication**

Add:

```python
def _publish_staged_directory(staged: Path, output: Path) -> None:
    backup = output.with_name(f".{output.name}.backup")
    if backup.exists():
        shutil.rmtree(backup)
    if output.exists():
        output.replace(backup)
    try:
        staged.replace(output)
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        if backup.exists():
            backup.replace(output)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)
```

Replace the current deletion/move loop with:

```python
_publish_staged_directory(chunks_root, output)
audit_path = _audit_path(output)
if audit_path.exists():
    audit_path.unlink()
```

The temporary directory is created under `output.parent`, so both renames remain on the same filesystem. No request can observe a mixture of old and new individual chunk files.

- [ ] **Step 8: Run all chunk-builder tests and verify GREEN**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_chunks.py -v -p no:cacheprovider
```

Expected: all geometry, alignment, audit, series validation, limit and publication tests pass.

- [ ] **Step 9: Commit the complete audited builder**

```powershell
git add -- scripts/build_township_chunks.py backend/tests/test_township_chunks.py
git diff --cached --name-only
git diff --cached --check
git commit -m "feat: publish audited current-county township chunks"
```

Expected staged files: exactly the two files listed above.

---

### Task 6: Wire the CLI and Rebuild the Real Township Dataset

**Files:**
- Modify: `scripts/build_township_chunks.py:32-39,270-289`
- Generate locally: `data/vectors/irrigation/township_by_county/*.geojson`
- Generate locally on failure only: `data/vectors/irrigation/township_by_county.alignment-audit.json`

**Interfaces:**
- Produces CLI options: `--county-source`, `--series`, `--exclude-file`.
- Default current county source: `F:\矢量底图\中国_县\中国_县.shp`.
- Default series source: `data/stats/irrigation_region_series.json`.
- Exclusion file schema: JSON object `{ "<12-digit-township-id>": "non-empty audit reason" }`.

- [ ] **Step 1: Add CLI parsing helpers and exact defaults**

Add constants:

```python
DEFAULT_COUNTY_SOURCE = Path(r"F:\矢量底图\中国_县\中国_县.shp")
DEFAULT_SERIES = PROJECT_ROOT / "data" / "stats" / "irrigation_region_series.json"
```

Add:

```python
def _load_exclusion_file(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Exclusion file must contain a JSON object")
    return validate_exclusions({str(key): str(value) for key, value in payload.items()})
```

Extend argparse and the call:

```python
parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
parser.add_argument("--county-source", type=Path, default=DEFAULT_COUNTY_SOURCE)
parser.add_argument("--series", type=Path, default=DEFAULT_SERIES)
parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
parser.add_argument("--exclude-file", type=Path)

manifest = build_chunks(
    args.source.resolve(),
    args.county_source.resolve(),
    args.series.resolve(),
    args.output.resolve(),
    args.tolerance,
    args.max_bytes,
    args.max_features,
    args.force,
    exclusions=_load_exclusion_file(args.exclude_file),
)
```

- [ ] **Step 2: Add and run a CLI parsing test**

Add to `backend/tests/test_township_chunks.py`:

```python
def test_exclusion_file_is_a_reasoned_id_mapping(tmp_path):
    path = tmp_path / "excluded.json"
    path.write_text(json.dumps({
        "231121100001": "unsupported source jurisdiction",
    }), encoding="utf-8")

    assert builder._load_exclusion_file(path) == {
        "231121100001": "unsupported source jurisdiction",
    }
```

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_chunks.py -v -p no:cacheprovider
python scripts/build_township_chunks.py --help
```

Expected: all tests pass and help lists all three new inputs.

- [ ] **Step 3: Commit the CLI before running the long data build**

```powershell
git add -- scripts/build_township_chunks.py backend/tests/test_township_chunks.py
git diff --cached --name-only
git diff --cached --check
git commit -m "feat: configure township county alignment inputs"
```

- [ ] **Step 4: Run the full forced rebuild**

From the repository root:

```powershell
$env:PYTHONPATH='.'
python scripts/build_township_chunks.py `
  --series "E:\遥感数据展示网站\data\stats\irrigation_region_series.json" `
  --force
```

Expected: exit code 0 and a summary with `alignment.unmatched=0`, `alignment.ambiguous=0`, `alignment.invalidGeometry=0`, `alignment.missingSeries=0`; `alignment.spatial` is greater than zero because obsolete county prefixes are remapped.

If the command exits nonzero, stop before API/browser verification, preserve the old formal output, and report the generated `township_by_county.alignment-audit.json`. Only entries whose jurisdiction is genuinely unsupported may be placed in a reviewed exclusion JSON with a concrete reason; ordinary unmatched or ambiguous features require fixing geometry/index logic or source data, not an exclusion guess.

- [ ] **Step 5: Validate current county coverage and hard limits**

```powershell
$root='data/vectors/irrigation/township_by_county'
$manifest=Get-Content "$root/manifest.json" -Raw | ConvertFrom-Json
if (-not (Test-Path "$root/231183.geojson")) { throw 'missing current Nenjiang chunk 231183' }
if ($manifest.maxChunkBytes -gt 1000000) { throw 'chunk byte limit exceeded' }
if ($manifest.maxChunkFeatures -gt 499) { throw 'feature limit exceeded' }
if ($manifest.alignment.unmatched -ne 0 -or
    $manifest.alignment.ambiguous -ne 0 -or
    $manifest.alignment.invalidGeometry -ne 0 -or
    $manifest.alignment.missingSeries -ne 0) {
  throw 'manifest contains unresolved alignment failures'
}
$manifest | Select-Object chunkCount,featureCount,townshipIdCount,maxChunkBytes,maxChunkFeatures,alignment
```

Expected: `231183.geojson` exists; maximums satisfy both limits; unresolved counts are zero.

- [ ] **Step 6: Verify the three user-reported county chunks through FastAPI**

```powershell
@'
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
for county_id, name in (
    ("156231183", "嫩江市"),
    ("156231124", "孙吴县"),
    ("156150782", "牙克石市"),
):
    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": county_id},
    )
    assert response.status_code == 200, (name, response.status_code, response.text)
    features = response.json()["features"]
    assert features, name
    assert all(item["properties"]["parentId"] == county_id for item in features)
    print(name, county_id, len(features))
'@ | python -
```

Expected: all three return 200 with at least one township and current county `parentId`.

Generated chunk files remain local/ignored. Do not stage thousands of GeoJSON files unless the repository policy is explicitly changed by the user.

---

### Task 7: Run Complete Automated and Browser Verification

**Files:**
- Modify only for recorded evidence: `task_plan.md`, `findings.md`, `progress.md`

**Interfaces:**
- Consumes all prior tasks.
- Produces acceptance evidence for callback freshness, two-stage querying, three current-code county chunks, error separation, performance limits and non-regression.

- [ ] **Step 1: Run focused backend tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_township_chunks.py backend/tests/test_township_vector_api.py -v -p no:cacheprovider
```

Expected: all focused builder and API tests pass.

- [ ] **Step 2: Run the complete backend suite**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests -v -p no:cacheprovider
```

Expected: all backend tests pass. Record exact pass count and any existing warning separately.

- [ ] **Step 3: Run focused and complete frontend tests**

From `frontend`:

```powershell
npx vitest run src/test/MapView.test.tsx src/test/App.test.tsx
npx vitest run
```

Expected: all tests pass with no unhandled rejection; the stale-handler test proves an old Leaflet handler calls the latest callback.

- [ ] **Step 4: Run production build and lint**

From `frontend`:

```powershell
npm run build
npm run lint
```

Expected: build succeeds; lint introduces no new warnings. Record pre-existing warnings without relabeling them as new regressions.

- [ ] **Step 5: Verify real browser interaction with the browser-control skill**

Use the existing healthy local services if they still listen on 5173/8000; otherwise start the backend with PowerShell `$env:PYTHONPATH='.'` and Vite with its existing configuration without terminating unknown user processes.

For each of 嫩江市、孙吴县、牙克石市:

1. Open the irrigation page.
2. Enable “县级统计” and wait for the county layer.
3. Switch directly to “乡镇级统计”.
4. Click the county polygon and inspect network/state: one current-county township-vector request occurs; no `level=township&regionId=<countyId>` series request occurs.
5. Confirm the township pane gains paths and the county pane remains present and colored.
6. Click one township and confirm monthly and annual series requests use the township’s original 12-digit ID; charts render or the township’s genuine “暂无统计数据” state appears.
7. Click the next county and confirm only the detail layer switches.

Expected: none of the three county clicks shows the county-name “暂无统计数据”; all three display clickable township vectors.

- [ ] **Step 6: Verify vector-absence copy independently**

Run the coded-404 page test from Task 2 and the API 404 test from Task 3 once more. Confirm the UI displays “该县暂无乡镇矢量” and never “暂无统计数据” before a township click.

- [ ] **Step 7: Review final repository scope**

```powershell
git status --short
git diff --check
git log --oneline -8
```

Expected: no whitespace errors; each new commit contains only its task files; unrelated pre-existing modifications and untracked artifacts remain untouched.

- [ ] **Step 8: Record completion evidence**

Update the persistent planning files with:

- focused/full backend and frontend pass counts;
- build and lint results;
- manifest `chunkCount`, `featureCount`, `townshipIdCount`, maximum bytes/features and all alignment counts;
- 嫩江市、孙吴县、牙克石市 chunk feature counts;
- browser-observed request order and chart result;
- any environment-only limitation or pre-existing warning.

Do not claim completion until all acceptance items above have direct evidence.

---

## Execution Notes

- Execute in an isolated worktree created with the `using-git-worktrees` skill. Because `backend/township_chunks.py`, `backend/tests/test_township_chunks.py` and `scripts/build_township_chunks.py` are currently untracked baseline files, copy only these three reviewed files into the isolated worktree before Task 3/4; do not copy the rest of the dirty workspace.
- The current workspace has the authoritative modified `data/stats/irrigation_region_series.json`. In an isolated worktree, pass its absolute path through `--series "E:\遥感数据展示网站\data\stats\irrigation_region_series.json"` as a read-only Task 6 input; do not copy or commit the 241 MB file. After the implementation branch is integrated, rerun the same forced build in the target workspace so its ignored chunk directory receives the validated current-code output.
- Preserve vector-first loading: publish a successful township chunk before awaiting township averages.
- Preserve the last successful township detail layer when a different county load fails.
- Do not change React-Leaflet `GeoJSON` keys to force remounts; the regression test must exercise the original layer handler.
- Do not use the township ID prefix as an output county decision. It is only a label for `direct` after the unique spatial match has already succeeded.
- If the real alignment audit is nonempty, stop and review it; do not weaken unique matching or add bulk exclusions merely to make the build pass.
