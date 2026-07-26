# 整体示范区域与点位尺寸调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将四个复耕示范区域合并为一个整体入口并把 Canvas 圆框半径调整为 450 米。

**Architecture:** 保留现有四个区域的静态点位接口，前端生成整体区域元数据，点击整体区域时并行请求四份点位数据并合并到一个缓存项。地图概览继续绘制现有矢量，但所有高亮面共享同一个选择回调；选中后用整体边界缩放。Canvas 只改半径常量，保留现有分桶命中和图例样式。

**Tech Stack:** React + TypeScript + React Leaflet + Vitest + Testing Library。

## Global Constraints

- 单位保持 `thousand_usd`，界面显示“千美元”。
- 不新增后端大文件或新的服务端合并负载。
- 点位只来自四个示范矢量内已分配的数据。
- 圆框最小半径仍为 3px，场景颜色、悬停和点击行为保持不变。

---

### Task 1: Lock the requested behavior with failing tests

**Files:**
- Modify: `frontend/src/test/ReclamationPage.test.tsx`
- Modify: `frontend/src/test/reclamationCanvas.test.ts`

**Interfaces:**
- Tests expect one overview entry named `进入示范区域`.
- Tests expect one overall points request cycle to call all four region IDs and merge their points.
- Tests expect `RECLAMATION_RADIUS_METERS` to be `450` and high-zoom circles to remain larger than the minimum.

- [ ] **Step 1: Change the page fixture assertions**

Replace the two mock region selector buttons with one `进入示范区域` button, provide four overview features in the fixture, and assert that clicking the button calls `getReclamationPoints` once for each fixture region ID and exposes the merged point count.

- [ ] **Step 2: Run the focused page test to verify it fails**

Run: `npm --prefix frontend run test -- src/test/ReclamationPage.test.tsx`

Expected: FAIL because the page currently renders one button per region and requests only one region ID.

- [ ] **Step 3: Update the radius expectation**

Change the Canvas test name and assertion from `564.19` to `450` while retaining the `circleRadiusPixels(40, 4) === 3` and high-zoom assertion.

- [ ] **Step 4: Run the focused Canvas test to verify it fails**

Run: `npm --prefix frontend run test -- src/test/reclamationCanvas.test.ts`

Expected: FAIL because production code still exports `564.19`.

### Task 2: Implement one overall region selection and merged point loading

**Files:**
- Modify: `frontend/src/pages/ReclamationPage.tsx`
- Modify: `frontend/src/components/ReclamationMap.tsx`

**Interfaces:**
- Add a page-local overall region with `id: 'DEMO'`, `name: '示范区域'`, summed `pointCount`, and bounds spanning all overview features.
- `selectRegion` handles `DEMO` by calling `getReclamationPoints` for every overview feature ID with the same AbortSignal, then stores a merged `ReclamationPointsResponse` in the existing cache.
- `ReclamationMap` calls `onRegionSelect` for any overview polygon and renders all overview features in selected mode.

- [ ] **Step 1: Add overall-region construction**

Implement a pure helper in `ReclamationPage.tsx` that reduces `overview.regions.features` to:

```ts
{
  id: 'DEMO',
  name: '示范区域',
  pointCount: features.reduce((sum, feature) => sum + feature.properties.pointCount, 0),
  bounds: [[minLatitude, minLongitude], [maxLatitude, maxLongitude]],
}
```

- [ ] **Step 2: Implement the aggregate request path**

When `region.id === 'DEMO'`, call `Promise.all(overview.regions.features.map(({ properties }) => getReclamationPoints(properties.id, signal)))`, flatten the returned `points`, and retain the shared `schemaVersion`, `unit`, and `fields` in a single response whose `region` is the overall region.

- [ ] **Step 3: Render one overview entry and unify map clicks**

Render only one button with accessible name `选择示范区域` and visible label `进入示范区域`; pass the overall region to both the button and the map callback. In `ReclamationMap`, suppress per-feature selection differences by sending all overview polygon clicks to the same callback and by using all features for selected rendering.

- [ ] **Step 4: Run the focused page tests to verify they pass**

Run: `npm --prefix frontend run test -- src/test/ReclamationPage.test.tsx`

Expected: PASS, including merged point count, scenario reset, retry, cache, and keyboard behavior.

### Task 3: Reduce Canvas circle size

**Files:**
- Modify: `frontend/src/components/reclamationCanvas.ts`

**Interfaces:**
- Set `RECLAMATION_RADIUS_METERS = 450`.
- Keep `MIN_RADIUS_PX = 3`, `SCREEN_BUCKET_PX = 32`, and the existing hit radius calculation.

- [ ] **Step 1: Change the radius constant**

Update only the exported radius constant from `564.19` to `450`.

- [ ] **Step 2: Run the focused Canvas tests**

Run: `npm --prefix frontend run test -- src/test/reclamationCanvas.test.ts`

Expected: PASS, including draw, hit-test, hover, and value-class tests.

### Task 4: Full verification and branch checkpoint

**Files:**
- No additional source files.

- [ ] **Step 1: Run the frontend test suite**

Run: `npm --prefix frontend run test`

Expected: all frontend tests pass.

- [ ] **Step 2: Run lint and production build**

Run: `npm --prefix frontend run lint` and `npm run build`

Expected: lint exits 0 with only the known pre-existing warning, and Vite build completes successfully.

- [ ] **Step 3: Review diff and commit implementation**

Run: `git diff --check; git status --short`

Then commit with: `git add frontend/src/pages/ReclamationPage.tsx frontend/src/components/ReclamationMap.tsx frontend/src/components/reclamationCanvas.ts frontend/src/test/ReclamationPage.test.tsx frontend/src/test/reclamationCanvas.test.ts && git commit -m "fix: combine reclamation demo region"`

