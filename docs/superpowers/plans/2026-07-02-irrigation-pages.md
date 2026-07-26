# Irrigation Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add top-level navigation for four platform sections and implement the irrigation water data display section with raster controls, county/village statistics, and a time-series chart.

**Architecture:** Keep the existing base map page intact and route it as the base-data section. Add a focused irrigation backend router that reads small JSON metadata/stat files and a frontend page that consumes those endpoints. Reuse the existing `MapView`, `Legend`, and API service patterns.

**Tech Stack:** FastAPI, JSON data files, React, React Router, Vitest, Testing Library, SVG for the line chart.

---

### Task 1: Backend Irrigation API

**Files:**
- Create: `backend/routers/irrigation.py`
- Modify: `backend/main.py`
- Modify: `backend/data_loader.py`
- Create: `backend/tests/test_irrigation.py`
- Create: `data/metadata/irrigation_layer.json`
- Create: `data/series/irrigation_annual_times.json`
- Create: `data/series/irrigation_8day_times.json`
- Create: `data/stats/irrigation_regions.json`
- Create: `data/stats/irrigation_region_series.json`

- [ ] Write failing tests for `/api/irrigation/layer`, `/api/irrigation/regions`, and `/api/irrigation/series`.
- [ ] Run `python -m pytest backend/tests/test_irrigation.py -v` and confirm the endpoints are missing.
- [ ] Add JSON loaders and the irrigation router.
- [ ] Register the router in `backend/main.py`.
- [ ] Add sample JSON data using the target file contract.
- [ ] Re-run `python -m pytest backend/tests/test_irrigation.py -v` and confirm it passes.

### Task 2: Frontend API And Types

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/test/api.test.ts`

- [ ] Write failing tests for irrigation API service helpers.
- [ ] Run `cd frontend && npx vitest run src/test/api.test.ts` and confirm the helpers are missing.
- [ ] Add irrigation region, period, and series types.
- [ ] Add `getIrrigationLayer`, `getIrrigationTimes`, `getIrrigationRegions`, and `getIrrigationSeries`.
- [ ] Re-run the API test file and confirm it passes.

### Task 3: Frontend Navigation And Pages

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Header.tsx`
- Create: `frontend/src/pages/IrrigationPage.tsx`
- Create: `frontend/src/pages/PlaceholderPage.tsx`
- Modify: `frontend/src/test/App.test.tsx`
- Modify: `frontend/src/App.css`

- [ ] Write failing UI tests for the four navigation items and irrigation page controls.
- [ ] Run `cd frontend && npx vitest run src/test/App.test.tsx` and confirm the UI is missing.
- [ ] Add navigation links in `Header`.
- [ ] Route `/`, `/base`, `/irrigation`, `/reclamation`, and `/water-demand`.
- [ ] Implement the irrigation page with raster controls, region selectors, stat period controls, summary, and an SVG line chart.
- [ ] Implement compact placeholder pages for the two deferred modules.
- [ ] Re-run the App test file and confirm it passes.

### Task 4: Final Verification

**Files:**
- All files touched above.

- [ ] Run `python -m pytest backend/tests/test_irrigation.py -v`.
- [ ] Run `cd frontend && npx vitest run src/test/api.test.ts src/test/App.test.tsx`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Inspect `git status --short` and summarize only files changed for this feature.
