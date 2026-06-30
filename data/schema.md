# Data Schema Documentation

This document describes the JSON schema for each data file type used by the
Remote Sensing Data Display Website. Backend API responses (Task 3) and
frontend consumers (Tasks 4-7) depend on these contracts.

---

## layers.json — Layer Metadata

**File**: `data/metadata/layers.json`
**Type**: JSON array of layer objects

Each layer object:

| Field          | Type   | Required | Description                                      |
|----------------|--------|----------|--------------------------------------------------|
| `id`           | string | yes      | Unique layer identifier (`ndvi`, `precipitation`, etc.) |
| `name`         | string | yes      | Human-readable display name                      |
| `description`  | string | no       | Longer description of the layer                  |
| `type`         | string | yes      | Category: `vegetation`, `climate`, `soil`, `temperature` |
| `unit`         | string | yes      | Unit of measurement (`index`, `mm`, `%`, `°C`)   |
| `range`        | object | yes      | `{ "min": number, "max": number }` expected data range |
| `timeRange`    | object | yes      | `{ "start": "YYYY-MM", "end": "YYYY-MM", "step": "month" }` |
| `tileTemplate` | string | yes      | URL/path template with `{time}`, `{z}`, `{x}`, `{y}` placeholders |
| `legend`       | array  | yes      | Array of `{ "value": number, "color": "#hex", "label": string }` gradient stops |

Validation rules:
- `id` must match `^[a-z][a-z0-9_]*$`
- `legend` must have at least 3 entries
- Every legend stop must have a numeric `value`
- Legend stop values must be unique within each layer
- All `color` values must be valid hex colors (`#rrggbb`)
- `timeRange.step` must be `"month"` (current MVP constraint)

---

## *_times.json — Time Points

**Files**: `data/series/ndvi_times.json`, `data/series/precipitation_times.json`,
`data/series/soil_moisture_times.json`, `data/series/lst_times.json`
**Type**: JSON array of strings

```json
["2025-01", "2025-02", "2025-03"]
```

Validation rules:
- Each entry must match `^\d{4}-\d{2}$` (YYYY-MM format)
- Entries must be sorted chronologically
- No duplicate entries

---

## *_series.json — Time Series Data

**Files**: `data/series/ndvi_series.json`, `data/series/precipitation_series.json`,
`data/series/soil_moisture_series.json`, `data/series/lst_series.json`
**Type**: JSON array of data point objects

Each data point:

| Field   | Type   | Required | Description                          |
|---------|--------|----------|--------------------------------------|
| `time`  | string | yes      | Time stamp in `YYYY-MM` format       |
| `value` | number | yes      | Mean value for the time point        |

Validation rules:
- `time` must match `^\d{4}-\d{2}$`
- `value` must be a finite number (not NaN, not Infinity)
- Values must fall within the layer's expected `range` (defined in layers.json)
- Entries should be sorted chronologically

---

## regions.json — Region Definitions

**File**: `data/stats/regions.json`
**Type**: JSON array of region objects

Each region object:

| Field         | Type   | Required | Description                          |
|---------------|--------|----------|--------------------------------------|
| `id`          | string | yes      | Unique region identifier (snake_case) |
| `name`        | string | yes      | Human-readable name (Chinese or English) |
| `description` | string | no       | Longer description of the region     |
| `bounds`      | object | yes      | `{ "north": number, "south": number, "east": number, "west": number }` |

Validation rules:
- `id` must match `^[a-z][a-z0-9_]*$`
- `bounds.north > bounds.south`
- `bounds.east > bounds.west`
- All bounds values must be in valid longitude/latitude ranges:
  - north/south: [-90, 90]
  - east/west: [-180, 180]

---

## area_stats.json — Area Statistics

**File**: `data/stats/area_stats.json`
**Type**: JSON object keyed by region ID, then layer ID, then time stamp

```json
{
  "region_id": {
    "layer_id": {
      "time_stamp": {
        "mean": 0.62,
        "max": 0.86,
        "min": 0.21,
        "count": 1280
      }
    }
  }
}
```

Each stat object:

| Field   | Type    | Required | Description                               |
|---------|---------|----------|-------------------------------------------|
| `mean`  | number  | yes      | Arithmetic mean of pixel values           |
| `max`   | number  | yes      | Maximum pixel value                       |
| `min`   | number  | yes      | Minimum pixel value                       |
| `count` | integer | yes      | Number of valid pixels in the region      |

Validation rules:
- `region_id` must exist in `regions.json`
- `layer_id` must match a layer `id` in `layers.json`
- `time_stamp` must match `^\d{4}-\d{2}$`
- `min <= mean <= max`
- `count > 0`
- Values must fall within the layer's expected `range`

---

## File Listing

| File | Rows | Size (approx) | Description |
|------|------|---------------|-------------|
| `data/metadata/layers.json` | ~60 | ~3 KB | 4 layer definitions with legends |
| `data/series/ndvi_times.json` | 1 | ~150 B | 12 monthly time points |
| `data/series/precipitation_times.json` | 1 | ~150 B | 12 monthly time points |
| `data/series/soil_moisture_times.json` | 1 | ~150 B | 12 monthly time points |
| `data/series/lst_times.json` | 1 | ~150 B | 12 monthly time points |
| `data/series/ndvi_series.json` | 12 | ~500 B | NDVI values for North China Plain |
| `data/series/precipitation_series.json` | 12 | ~500 B | Precipitation values for North China Plain |
| `data/series/soil_moisture_series.json` | 12 | ~500 B | Soil moisture values for North China Plain |
| `data/series/lst_series.json` | 12 | ~500 B | LST values for North China Plain |
| `data/stats/regions.json` | ~30 | ~1.5 KB | 4 predefined regions |
| `data/stats/area_stats.json` | ~60 | ~3 KB | Stats for 4 regions × 4 layers × 3 time points |
