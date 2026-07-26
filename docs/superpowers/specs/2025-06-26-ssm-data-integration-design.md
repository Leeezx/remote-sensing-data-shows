# SSM Data Integration Design

**Date**: 2025-06-26
**Status**: draft
**Source**: 181 GeoTIFF files from `F:/全国灌溉用水反演/数据2010-2013/SSM预测结果/`

## Overview

Integrate real Surface Soil Moisture (SSM) time-series raster data into the remote sensing display website. The data spans 2010-2013 at 8-day resolution, in EPSG:4326, with values 0.09-0.39 m³/m³ and ~2.6% valid pixels (irrigation areas only).

Files are named `YYYY_NN.tif` where NN is the 8-day period index within the year (1-indexed, starting Jan 1). E.g., `2010_05` = year 2010, 5th 8-day period (approx Jan 29-Feb 5).

## Architecture

### Processing Pipeline (offline, one-time, using `irrigation_water` conda env with GDAL 3.9)

**Phase 1 — 8-day statistics (181 files)**
- For each TIFF: `gdal_translate -stats` → extract min, max, mean, stddev, valid_pct
- Parse file name → compute actual date range (`YYYY_NN` → start date of 8-day period)
- Output: `data/series/ssm_8day_times.json`, `data/series/ssm_8day_series.json`

**Phase 2 — Monthly aggregation & tile generation (48 months)**
- Group 8-day files by year-month
- For each month: merge 4-5 files into a monthly mean GeoTIFF via `gdal_calc.py` or rasterio
- Reproject to EPSG:3857 via `gdalwarp`
- Generate tile pyramid (zoom 0-6) via `gdal2tiles.py` into `data/tiles/ssm/{YYYY-MM}/`
- Extract monthly stats → `data/series/ssm_times.json`, `data/series/ssm_series.json`

### Layer Definition

Add to `data/metadata/layers.json`:

```json
{
  "id": "ssm",
  "name": "表层土壤水分",
  "description": "Surface Soil Moisture (0-5cm) from SSM prediction model, 8-day composite",
  "type": "soil",
  "unit": "m³/m³",
  "range": { "min": 0.0, "max": 0.5 },
  "timeRange": { "start": "2010-01", "end": "2013-12", "step": "month" },
  "tileTemplate": "data/tiles/ssm/{time}/{z}/{x}/{y}.png",
  "legend": [
    { "color": "#d53e4f", "label": "dry (0.09)" },
    { "color": "#fc8d59", "label": "low (0.15)" },
    { "color": "#fee08b", "label": "moderate (0.22)" },
    { "color": "#99d594", "label": "moist (0.28)" },
    { "color": "#3288bd", "label": "wet (0.35)" },
    { "color": "#016c59", "label": "saturated (0.40)" }
  ]
}
```

### Output Files

```
data/
├── metadata/layers.json              ← add ssm entry
├── series/
│   ├── ssm_times.json                ← 48 monthly time points (YYYY-MM)
│   ├── ssm_series.json               ← 48 monthly mean values
│   ├── ssm_8day_times.json           ← 181 8-day time points (YYYY-MM-DD)
│   └── ssm_8day_series.json          ← 181 8-day mean values
├── tiles/ssm/
│   ├── 2010-01/{0..6}/{x}/{y}.png
│   ├── 2010-02/{0..6}/{x}/{y}.png
│   └── ...                           ← 48 monthly tile sets
```

### Frontend Changes

- Layer selector picks up `ssm` from `/api/layers` automatically — no code changes needed
- The 8-day series is NOT consumed by the existing `/series` endpoint (which expects monthly). Add a new endpoint `/api/layers/{layer_id}/times?resolution=8day` to serve 8-day time points for chart use, or expose it through the existing `/series` endpoint with a `resolution` query parameter.
- ChartPanel needs to handle variable time-step labels (8-day dates look different from monthly "YYYY-MM").

### Backend Changes

- `data_loader.py`: add `get_layer_times(layer_id, resolution='month')` and `get_series(layer_id, resolution='month')` to support 8-day resolution
- `routers/series.py`: add `resolution` query parameter
- `routers/layers.py`: support `resolution` parameter for `/times` endpoint

## Dependencies

- GDAL 3.9+ (from `irrigation_water` conda env)
- rasterio (from same env)
- Processing time: ~30 minutes for all 48 monthly tile sets + 181 stats

## Edge Cases & Constraints

- **Sparse data**: Only ~2.6% pixels valid — tiles outside irrigation areas will be transparent
- **NoData**: Original TIFF has no NoData tag; NaN values serve as NoData. Script must handle NaN → transparency in tile generation.
- **File naming gaps**: Need to verify all 8-day periods are present (1-46 per year × 4 years = 184 expected, 181 present — minor gaps acceptable)
- **Cross-year boundary**: December files may span into next January; monthly grouping by file start date is sufficient
- **Raw values**: TIFF stores raw float32 (0.09-0.39 m³/m³), no scale/offset needed
