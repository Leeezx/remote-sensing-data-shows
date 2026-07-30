# Irrigation Administrative Interaction Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore reliable county/township hover and click behavior, reuse the mounted county layer across admin-mode switches, and make irrigation region series strictly JSON-backed.

**Architecture:** Give county and township GeoJSON overlays fixed Leaflet panes and make hover restoration deterministic without changing layer order. Treat county vector/averages as one administrative-session resource whose lifetime is `regionLevel !== null`, while township detail remains per-county. The backend series route reads only `data/stats/irrigation_region_series.json` and returns 404 for missing JSON data.

**Tech Stack:** React 19, TypeScript, React-Leaflet/Leaflet, Vitest/Testing Library, FastAPI, pytest.

## Global Constraints

- Preserve all unrelated dirty-worktree changes.
- Do not regenerate administrative JSON or vector chunks.
- Do not change raster query behavior outside administrative statistics mode.
- County and township colors continue to use the existing annual-average legend thresholds.
- Every production change follows RED → GREEN and receives focused regression coverage.

---

### Task 1: Make Region Hover Deterministic and Keep Township Events Above Counties

**Files:**
- Modify: `frontend/src/components/MapView.tsx:1-490`
- Test: `frontend/src/test/MapView.test.tsx:1-430`

**Interfaces:**
- Produces: `RegionOverlay` prop `pane: string`.
- Produces: panes named `county-regions` and `township-regions` with township z-index greater than county z-index.
- Preserves: `onRegionSelect`, `colorMap`, `selectedRegionId`, and the 499-feature township guard.

- [ ] **Step 1: Extend the React-Leaflet test mock to capture pane and feature events**

Add `Pane` and richer GeoJSON bookkeeping to `frontend/src/test/MapView.test.tsx`:

```tsx
interface FeatureLayerMocks {
  id: string
  pane: string | undefined
  handlers: Record<string, (event?: { originalEvent?: Event }) => void>
  setStyle: ReturnType<typeof vi.fn>
  bringToFront: ReturnType<typeof vi.fn>
}

// Inside mapMocks:
featureLayers: [] as FeatureLayerMocks[],
panes: [] as Array<{ name: string; zIndex: number | string | undefined }>,

// Inside vi.mock('react-leaflet'):
Pane: ({ name, style, children }: {
  name: string
  style?: { zIndex?: number | string }
  children: ReactNode
}) => {
  mapMocks.panes.push({ name, zIndex: style?.zIndex })
  return <>{children}</>
},
GeoJSON: ({ data, onEachFeature, pane }: {
  data: { features: VectorFeature[] }
  pane?: string
  onEachFeature: (feature: VectorFeature, layer: {
    on: (handlers: Record<string, (event?: { originalEvent?: Event }) => void>) => void
    setStyle: ReturnType<typeof vi.fn>
    bringToFront: ReturnType<typeof vi.fn>
    unbindTooltip: ReturnType<typeof vi.fn>
  }) => void
}) => {
  for (const feature of data.features) {
    const handlers: Record<string, (event?: { originalEvent?: Event }) => void> = {}
    const setStyle = vi.fn()
    const bringToFront = vi.fn()
    onEachFeature(feature, {
      on: (next) => Object.assign(handlers, next),
      setStyle,
      bringToFront,
      unbindTooltip: vi.fn(),
    })
    mapMocks.featureLayers.push({
      id: feature.properties.id,
      pane,
      handlers,
      setStyle,
      bringToFront,
    })
  }
  return <div data-testid="region-geojson" />
},
```

Reset both arrays in `beforeEach`.

- [ ] **Step 2: Add failing hover-restoration and pane-order tests**

Add tests that render county and township vectors together:

```tsx
it('restores county color after hover without moving the layer to front', () => {
  const countyColorMap = new Map([['county_a', '#2563eb']])
  render(<MapView
    {...baseProps}
    regionVector={vectorFixture('county_a', '示范县A')}
    regionLevel="county"
    regionColorMap={countyColorMap}
    onRegionSelect={vi.fn()}
  />)

  const layer = mapMocks.featureLayers.find((item) => item.id === 'county_a')!
  act(() => layer.handlers.mouseover?.())
  expect(layer.setStyle).toHaveBeenLastCalledWith(expect.objectContaining({ fillColor: '#14b8a6' }))

  act(() => layer.handlers.mouseout?.())
  expect(layer.setStyle).toHaveBeenLastCalledWith(expect.objectContaining({ fillColor: '#2563eb' }))
  expect(layer.bringToFront).not.toHaveBeenCalled()
})

it('renders township features in a higher fixed pane and forwards their click', () => {
  const onTownshipSelect = vi.fn()
  render(<MapView
    {...baseProps}
    regionVector={vectorFixture('county_a', '示范县A')}
    regionLevel="county"
    onRegionSelect={vi.fn()}
    detailRegionVector={vectorFixture('township_a1', '示范镇A1')}
    detailRegionLevel="township"
    onDetailRegionSelect={onTownshipSelect}
  />)

  const countyPane = mapMocks.panes.find((item) => item.name === 'county-regions')!
  const townshipPane = mapMocks.panes.find((item) => item.name === 'township-regions')!
  expect(Number(townshipPane.zIndex)).toBeGreaterThan(Number(countyPane.zIndex))

  const township = mapMocks.featureLayers.find((item) => item.id === 'township_a1')!
  act(() => township.handlers.mouseover?.())
  expect(township.setStyle).toHaveBeenCalled()
  act(() => township.handlers.click?.({ originalEvent: new MouseEvent('click') }))
  expect(onTownshipSelect).toHaveBeenCalledWith({ id: 'township_a1', name: '示范镇A1' })
})
```

Define `vectorFixture(id, name)` locally using a one-feature Polygon FeatureCollection.

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```powershell
cd frontend
npx vitest run src/test/MapView.test.tsx -t "restores county color|higher fixed pane"
```

Expected: FAIL because `RegionOverlay` has no pane prop and hover calls `bringToFront()`.

- [ ] **Step 4: Add fixed panes and remove hover z-order mutation**

Import `Pane` from `react-leaflet`. Add a required pane prop to `RegionOverlay` and pass it to `GeoJSON`:

```tsx
function RegionOverlay({ pane, ...props }: {
  pane: string
  // retain the existing data, selection, callback, color-map and level props
}) {
  // existing implementation
  return (
    <GeoJSON
      pane={pane}
      data={data as never}
      style={featureStyle}
      onEachFeature={(feature, layer) => {
        geoLayersRef.current.push(layer)
        layer.on({
          mouseover: () => {
            ;(layer as L.Path).setStyle({
              color: '#0f766e',
              opacity: 0.85,
              weight: 2.4,
              fillColor: '#14b8a6',
              fillOpacity: 0.16,
            })
          },
          mouseout: () => {
            ;(layer as L.Path).setStyle(featureStyle(feature))
          },
          click: (event) => {
            if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent)
            const id = String(feature.properties?.id ?? feature.properties?.gb ?? feature.properties?.name ?? '')
            const name = String(feature.properties?.name ?? feature.properties?.NAME ?? id)
            if (id) onRegionSelect({ id, name })
          },
        })
      }}
    />
  )
}
```

Do not call `bringToFront()` from hover. Wrap the two overlays in fixed panes:

```tsx
<Pane name="county-regions" style={{ zIndex: 410 }}>
  <RegionOverlay pane="county-regions" {...countyOverlayProps} />
</Pane>
<Pane name="township-regions" style={{ zIndex: 420 }}>
  <RegionOverlay pane="township-regions" {...townshipOverlayProps} />
</Pane>
```

- [ ] **Step 5: Run focused and full MapView tests**

Run:

```powershell
cd frontend
npx vitest run src/test/MapView.test.tsx
```

Expected: all MapView tests PASS, including query reset and the 499-feature guard.

- [ ] **Step 6: Commit the map interaction fix**

```powershell
git add -- frontend/src/components/MapView.tsx frontend/src/test/MapView.test.tsx
git diff --cached --check
git commit -m "fix: restore irrigation region hover interactions"
```

---

### Task 2: Reuse County Data Across Admin Modes and Restore Township Statistics

**Files:**
- Modify: `frontend/src/pages/IrrigationPage.tsx:127-620`
- Test: `frontend/src/test/App.test.tsx:1-480`

**Interfaces:**
- Consumes: Task 1 independent primary/detail overlay events.
- Produces: county base-data lifetime controlled by `isAdminStatsMode`, not the exact `regionLevel`.
- Produces: `toggleAdminMode(target: IrrigationRegionLevel): void` for atomic mode transitions.

- [ ] **Step 1: Add a failing no-reload mode-switch test**

Add to `frontend/src/test/App.test.tsx`:

```tsx
it('reuses the mounted county layer when switching from county to township statistics', async () => {
  window.history.pushState({}, '', '/irrigation')
  const user = userEvent.setup()
  render(<App />)

  await user.click(await screen.findByRole('button', { name: '县级统计' }))
  await waitFor(() => expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded'))
  const vectorCalls = apiMocks.getIrrigationVectorGeoJSON.mock.calls
    .filter(([level]) => level === 'county').length
  const averageCalls = apiMocks.getIrrigationRegionAverages.mock.calls
    .filter(([level]) => level === 'county').length

  await user.click(screen.getByRole('button', { name: '乡镇级统计' }))

  expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
  expect(apiMocks.getIrrigationVectorGeoJSON.mock.calls.filter(([level]) => level === 'county'))
    .toHaveLength(vectorCalls)
  expect(apiMocks.getIrrigationRegionAverages.mock.calls.filter(([level]) => level === 'county'))
    .toHaveLength(averageCalls)
})
```

- [ ] **Step 2: Strengthen township selection and missing-data tests**

Extend the existing township test to assert both periods and rendered statistics:

```tsx
await user.click(screen.getByRole('button', { name: '选择示范镇A1' }))
await waitFor(() => {
  expect(apiMocks.getIrrigationSeries).toHaveBeenCalledWith('township', 'township_a1', 'monthly')
  expect(apiMocks.getIrrigationSeries).toHaveBeenCalledWith('township', 'township_a1', 'annual')
})
expect(screen.getByRole('img', { name: '示范镇A1 月度灌溉用水量折线图' })).toBeInTheDocument()
```

Add a missing-data case:

```tsx
it('keeps township layers visible when JSON statistics are unavailable', async () => {
  apiMocks.getIrrigationSeries.mockRejectedValueOnce({ response: { status: 404 } })
  const user = userEvent.setup()
  render(<App />)
  await user.click(await screen.findByRole('button', { name: '乡镇级统计' }))
  await user.click(screen.getByRole('button', { name: '选择示范县A' }))
  await screen.findByText('已加载示范县A 1 个乡镇')
  await user.click(screen.getByRole('button', { name: '选择示范镇A1' }))

  expect(await screen.findByText('暂无统计数据')).toBeInTheDocument()
  expect(screen.getByTestId('county-layer')).toHaveTextContent('loaded')
  expect(screen.getByTestId('township-layer')).toHaveTextContent('loaded')
})
```

- [ ] **Step 3: Run page regressions and verify RED**

Run:

```powershell
cd frontend
npx vitest run src/test/App.test.tsx -t "reuses the mounted county layer|loads townships only|JSON statistics are unavailable"
```

Expected: the mode-switch test reports an extra county load, and the 404 case shows the generic availability error.

- [ ] **Step 4: Make county base-data lifetime depend only on admin-mode activation**

Move this derived flag before the base-data effect:

```tsx
const isAdminStatsMode = regionLevel !== null
```

Change the county vector/averages effect dependency from `regionLevel` to `isAdminStatsMode`. When `isAdminStatsMode` changes from false to true, load `getIrrigationVectorStatus('county')`, `loadVector('county')`, and `getIrrigationRegionAverages('county')` once; do not clear county state when `regionLevel` changes between `county` and `township`. Clear county state only when `isAdminStatsMode` changes to false.

The effect skeleton must be:

```tsx
useEffect(() => {
  if (!isAdminStatsMode) {
    townshipRequestIdRef.current += 1
    setCountyVector(null)
    setCountyAverages([])
    setCountyLegend([])
    setCountyLegendStatus('loading')
    setTownshipVector(null)
    setTownshipCounty(null)
    setSelectedRegion(null)
    return
  }

  let cancelled = false
  setAdminStatsLoading(true)
  setCountyLegendStatus('loading')
  const vectorRequest = getIrrigationVectorStatus('county').then(async (status) => {
    if (cancelled) return
    setVectorStatus(status)
    if (!status.available) return
    const vector = await loadVector('county')
    if (!cancelled) setCountyVector(vector)
  }).catch(() => {
    if (!cancelled) setVectorStatus({
      level: 'county',
      available: false,
      url: null,
      message: '行政区矢量暂不可用',
    })
  })
  const averagesRequest = getIrrigationRegionAverages('county').then((result) => {
    if (cancelled) return
    setCountyAverages(result.averages)
    setCountyLegend(result.legend)
    setCountyLegendStatus('ready')
  }).catch(() => {
    if (!cancelled) setCountyLegendStatus('error')
  })
  void Promise.all([vectorRequest, averagesRequest]).finally(() => {
    if (!cancelled) setAdminStatsLoading(false)
  })
  return () => { cancelled = true }
}, [isAdminStatsMode, loadVector])
```

Because `regionLevel` is deliberately absent from the dependency list, county → township and township → county transitions retain the same county GeoJSON object and do not restart these requests.

- [ ] **Step 5: Make mode transitions atomic**

Add and use one callback for both buttons:

```tsx
const toggleAdminMode = useCallback((target: IrrigationRegionLevel) => {
  const nextLevel = regionLevel === target ? null : target
  townshipRequestIdRef.current += 1
  setSelectedRegion(null)
  setMonthlySeries(null)
  setAnnualSeries(null)
  setSeriesError('')

  if (nextLevel !== 'township') {
    setTownshipVector(null)
    setTownshipAverages([])
    setTownshipLegend([])
    setTownshipLegendStatus('loading')
    setTownshipCounty(null)
    setPendingTownshipCounty(null)
  }
  setRegionLevel(nextLevel)
}, [regionLevel])
```

Wire buttons with `onClick={() => toggleAdminMode('county')}` and `onClick={() => toggleAdminMode('township')}`. Switching county → township must not change `countyVector`, `countyAverages`, or `countyLegend`.

- [ ] **Step 6: Show a specific JSON-missing message while retaining layers**

Add a small status helper:

```tsx
function isNotFoundError(error: unknown): boolean {
  if (!error || typeof error !== 'object' || !('response' in error)) return false
  const response = (error as { response?: { status?: number } }).response
  return response?.status === 404
}
```

Update the series catch handler:

```tsx
.catch((error: unknown) => {
  if (!cancelled) {
    setMonthlySeries(null)
    setAnnualSeries(null)
    setSeriesError(isNotFoundError(error) ? '暂无统计数据' : '行政区灌溉用水统计暂不可用')
  }
})
```

Do not clear `selectedRegion`, `countyVector`, or `townshipVector` in this handler.

- [ ] **Step 7: Run focused and full page tests**

Run:

```powershell
cd frontend
npx vitest run src/test/App.test.tsx
```

Expected: all App tests PASS; county vector and averages each load once during county → township switching.

- [ ] **Step 8: Commit the page-state fix**

```powershell
git add -- frontend/src/pages/IrrigationPage.tsx frontend/src/test/App.test.tsx
git diff --cached --check
git commit -m "fix: reuse county data for township statistics"
```

---

### Task 3: Make Region Series Strictly JSON-backed

**Files:**
- Modify: `backend/routers/irrigation.py:1-295`
- Test: `backend/tests/test_irrigation.py:271-330`

**Interfaces:**
- Consumes: `get_irrigation_region_series() -> dict` from `backend/data_loader.py`.
- Produces: `GET /api/irrigation/series` returns 404 when the requested region or period is absent from JSON.
- Removes: route dependency on `compute_irrigation_region_series` for missing data.

- [ ] **Step 1: Replace the realtime-fallback test with JSON-only failures**

Replace `test_get_irrigation_series_computes_missing_vector_region` with:

```python
def test_get_irrigation_series_returns_404_without_realtime_fallback(monkeypatch):
    monkeypatch.setattr(
        irrigation_router,
        "find_irrigation_vector_feature",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("vector fallback must not run")
        ),
    )

    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "county",
            "regionId": "nonexistent_county_99999",
            "period": "annual",
        },
    )

    assert response.status_code == 404
    assert "not found in precomputed irrigation statistics" in response.json()["detail"]


def test_get_irrigation_series_returns_404_when_period_is_missing(monkeypatch):
    monkeypatch.setattr(
        irrigation_router,
        "get_irrigation_region_series",
        lambda: {
            "unit": "万m³",
            "county": {"county_without_month": {"annual": []}},
            "township": {},
        },
    )

    response = client.get(
        "/api/irrigation/series",
        params={
            "level": "county",
            "regionId": "county_without_month",
            "period": "monthly",
        },
    )

    assert response.status_code == 404
    assert "monthly" in response.json()["detail"]
```

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_irrigation.py -k "without_realtime or period_is_missing" -v -p no:cacheprovider
```

Expected: the missing-region test enters the current vector/realtime fallback and raises the assertion; missing-period behavior does not return the required JSON-only 404 message.

- [ ] **Step 3: Remove the realtime series fallback from the route**

Remove the `compute_irrigation_region_series` import from `backend/routers/irrigation.py`. Replace the current `try/except KeyError` block in `irrigation_series` with:

```python
    series_data = get_irrigation_region_series()
    level_data = series_data.get(level)
    region_data = level_data.get(regionId) if isinstance(level_data, dict) else None
    if not isinstance(region_data, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Irrigation {level} region '{regionId}' was not found "
                "in precomputed irrigation statistics"
            ),
        )

    series = region_data.get(period)
    if not isinstance(series, list):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Irrigation {period} series for {level} region "
                f"'{regionId}' was not found in precomputed irrigation statistics"
            ),
        )

    region = _find_region(regionId, level)
    if region is None:
        region = {
            "id": regionId,
            "name": str(region_data.get("name") or regionId),
            "level": level,
            "parentId": region_data.get("parentId"),
        }
```

Keep the existing summary calculation over `series`. Do not call vector readers, shapefile readers, raster readers, or `compute_irrigation_region_series`.

- [ ] **Step 4: Run focused backend tests**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_irrigation.py -v -p no:cacheprovider
```

Expected: all irrigation endpoint tests PASS, including existing county/township precomputed responses and both new 404 contracts.

- [ ] **Step 5: Commit the JSON-only API change**

```powershell
git add -- backend/routers/irrigation.py backend/tests/test_irrigation.py
git diff --cached --check
git commit -m "fix: query irrigation region series from JSON only"
```

---

### Task 4: Complete Regression Verification

**Files:**
- Verify only; no production file changes expected.

**Interfaces:**
- Verifies: all four reported behaviors and existing irrigation/query contracts.

- [ ] **Step 1: Run focused backend tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_irrigation.py backend/tests/test_precompute_irrigation.py backend/tests/test_township_chunks.py -v -p no:cacheprovider
```

Expected: all focused backend tests PASS.

- [ ] **Step 2: Run full backend tests**

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests -v -p no:cacheprovider
```

Expected: all backend tests PASS; existing NumPy deprecation warnings may remain.

- [ ] **Step 3: Run focused and full frontend tests**

```powershell
cd frontend
npx vitest run src/test/MapView.test.tsx src/test/App.test.tsx src/test/api.test.ts
npx vitest run
```

Expected: all frontend tests PASS without unhandled promise rejections.

- [ ] **Step 4: Run build and lint**

```powershell
cd frontend
npm run build
npm run lint
```

Expected: build and lint exit 0; the two known warnings in `AuthContext.tsx` and the TileOverlay opacity effect may remain unless changed by this plan.

- [ ] **Step 5: Verify no realtime path and no accidental data regeneration**

```powershell
rg -n "compute_irrigation_region_series" backend/routers/irrigation.py
git status --short -- data/stats data/vectors
git diff --check
```

Expected: the route contains no compute call; no new changes appear under `data/stats` or `data/vectors` from this plan; diff check exits 0.

- [ ] **Step 6: Review the final commit range**

```powershell
git log --oneline -5
git diff --stat 5e6e333..HEAD
```

Expected: only the map/test, page/test, and router/test commits described above appear after the design commit.
