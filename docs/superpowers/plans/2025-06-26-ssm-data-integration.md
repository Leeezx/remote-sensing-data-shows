# SSM Data Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process 181 SSM GeoTIFF files into JSON time series + PNG tiles, register as a new layer, and update backend/frontend to support 8-day resolution charts.

**Architecture:** One processing script (`scripts/process_ssm_data.py`) using `irrigation_water` conda env (GDAL 3.9, rasterio) to extract stats and generate tiles. Backend gains an optional `resolution` query parameter. Frontend gets minor label formatting improvements. Monthly tiles for map overlay, 8-day series for charts.

**Tech Stack:** Python 3.10 (irrigation_water env), GDAL 3.9, rasterio 1.4, numpy; FastAPI (backend); React + ECharts (frontend)

## Global Constraints

- Source TIFFs: `F:/全国灌溉用水反演/数据2010-2013/SSM预测结果/YYYY_NN.tif`
- File naming: `YYYY_NN` = year + 8-day period index (1-indexed from Jan 1)
- CRS: EPSG:4326 → tiles must be EPSG:3857 for Leaflet
- Processing env: `/c/ProgramData/miniconda3/envs/irrigation_water/python.exe`
- All new data files live under `data/` (existing conventions)
- `timeRange.step` in layers.json must remain `"month"` for the layer (monthly tiles)
- 8-day data served via `resolution=8day` query param on existing endpoints

---

### Task 1: Processing Script — 8-day Statistics

**Files:**
- Create: `scripts/process_ssm_data.py`
- Create: `data/series/ssm_8day_times.json`
- Create: `data/series/ssm_8day_series.json`

**Interfaces:**
- Consumes: TIFF files from source directory
- Produces: `ssm_8day_times.json` (array of "YYYY-MM-DD" strings), `ssm_8day_series.json` (array of `{"time": "YYYY-MM-DD", "value": float, "min": float, "max": float, "count": int}` objects)

**Script implementation:**

- [ ] **Step 1: Write the processing script (Phase 1 — 8-day stats extraction)**

Create `scripts/process_ssm_data.py`:

```python
#!/usr/bin/env python3
"""
Process SSM GeoTIFF files into JSON time series and PNG map tiles.

Usage:
    /c/ProgramData/miniconda3/envs/irrigation_water/python.exe scripts/process_ssm_data.py

Phases:
    1. Extract 8-day statistics → ssm_8day_times.json, ssm_8day_series.json
    2. Monthly aggregation + tile generation → ssm_times.json, ssm_series.json, tiles/ssm/
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.warp import calculate_default_transform, reproject, Resampling

# === Configuration ===
SOURCE_DIR = Path("F:/全国灌溉用水反演/数据2010-2013/SSM预测结果")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SERIES_DIR = DATA_DIR / "series"
TILES_DIR = DATA_DIR / "tiles" / "ssm"
TEMP_DIR = PROJECT_ROOT / "temp_ssm"

# GDAL executables from irrigation_water env
GDALWARP = "/c/ProgramData/miniconda3/envs/irrigation_water/Library/bin/gdalwarp.exe"
GDALDEM = "/c/ProgramData/miniconda3/envs/irrigation_water/Library/bin/gdaldem.exe"

# Color ramp for SSM visualization (matches legend in layers.json)
COLOR_RAMP = """0.09 213 62 79 255
0.15 252 141 89 255
0.22 254 224 139 255
0.28 153 213 148 255
0.35 50 136 189 255
0.40 1 108 89 255
nv 0 0 0 0
"""

# === Helpers ===

def parse_filename(filename: str) -> tuple[int, int]:
    """Parse '2010_05.tif' → (year=2010, period=5)."""
    stem = Path(filename).stem  # "2010_05"
    match = re.match(r"^(\d{4})_(\d{2,3})$", stem)
    if not match:
        raise ValueError(f"Cannot parse filename: {filename}")
    return int(match.group(1)), int(match.group(2))


def period_to_date(year: int, period: int) -> str:
    """Convert year + 8-day period index to start date string YYYY-MM-DD."""
    start = datetime(year, 1, 1) + timedelta(days=(period - 1) * 8)
    return start.strftime("%Y-%m-%d")


def date_to_year_month(date_str: str) -> str:
    """'2010-02-02' → '2010-02'."""
    return date_str[:7]


def get_file_stats(filepath: Path) -> dict:
    """Read a TIFF and return statistics (ignoring NaN)."""
    with rasterio.open(filepath) as src:
        arr = src.read(1)
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return {
                "mean": None, "min": None, "max": None,
                "count": 0, "dtype": str(src.dtypes[0]),
                "width": src.width, "height": src.height,
            }
        return {
            "mean": float(valid.mean()),
            "min": float(valid.min()),
            "max": float(valid.max()),
            "count": int(len(valid)),
            "dtype": str(src.dtypes[0]),
            "width": src.width,
            "height": src.height,
        }


# === Phase 1: 8-day Statistics ===

def extract_8day_stats(source_dir: Path) -> list[dict]:
    """Extract statistics for every 8-day TIFF file."""
    files = sorted(source_dir.glob("*.tif"))
    print(f"Found {len(files)} TIFF files in {source_dir}")

    records = []
    for i, fpath in enumerate(files):
        year, period = parse_filename(fpath.name)
        date_str = period_to_date(year, period)
        stats = get_file_stats(fpath)
        records.append({
            "time": date_str,
            "value": stats["mean"],
            "min": stats["min"],
            "max": stats["max"],
            "count": stats["count"],
            "file": fpath.name,
        })
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(files)}] {fpath.name} → {date_str} mean={stats['mean']}")

    # Sort by time
    records.sort(key=lambda r: r["time"])
    return records


def write_8day_json(records: list[dict]):
    """Write ssm_8day_times.json and ssm_8day_series.json."""
    SERIES_DIR.mkdir(parents=True, exist_ok=True)

    # Times file
    times = [r["time"] for r in records]
    times_path = SERIES_DIR / "ssm_8day_times.json"
    with open(times_path, "w", encoding="utf-8") as f:
        json.dump(times, f, ensure_ascii=False)
    print(f"Wrote {times_path} ({len(times)} entries)")

    # Series file
    series = [{"time": r["time"], "value": r["value"]} for r in records]
    series_path = SERIES_DIR / "ssm_8day_series.json"
    with open(series_path, "w", encoding="utf-8") as f:
        json.dump(series, f, ensure_ascii=False)
    print(f"Wrote {series_path} ({len(series)} entries)")


# === Phase 2: Monthly Aggregation & Tile Generation ===

def average_rasters(filepaths: list[Path], output_path: Path, nodata_val: float = -9999.0):
    """Average multiple GeoTIFF files (NaN-aware) into a single monthly composite."""
    arrays = []
    profile = None
    for fp in filepaths:
        with rasterio.open(fp) as src:
            arr = src.read(1)
            # Replace NaN with actual NaN (they might already be NaN)
            arrays.append(arr.copy())
            if profile is None:
                profile = src.profile.copy()

    # Stack and compute mean ignoring NaN
    stacked = np.stack(arrays, axis=0)
    with np.errstate(all='ignore'):
        monthly = np.nanmean(stacked, axis=0)

    # Replace remaining NaN (pixels that are NaN in ALL inputs) with NoData
    monthly[np.isnan(monthly)] = nodata_val

    # Update profile for output
    profile.update(
        dtype=rasterio.float32,
        count=1,
        nodata=nodata_val,
        compress='lzw',
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(monthly.astype(rasterio.float32), 1)

    # Return valid-pixel stats
    valid_mask = monthly != nodata_val
    if valid_mask.sum() > 0:
        return {
            "mean": float(monthly[valid_mask].mean()),
            "min": float(monthly[valid_mask].min()),
            "max": float(monthly[valid_mask].max()),
            "count": int(valid_mask.sum()),
        }
    return {"mean": None, "min": None, "max": None, "count": 0}


def generate_tiles(input_tif: Path, tile_output_dir: Path, zoom_range: str = "0-6"):
    """Generate XYZ tile pyramid from a GeoTIFF.

    Steps:
    1. gdalwarp → EPSG:3857
    2. gdaldem color-relief → RGBA with legend colors
    3. gdal2tiles.py → PNG tile pyramid
    """
    tile_output_dir.mkdir(parents=True, exist_ok=True)
    warped = input_tif.parent / f"{input_tif.stem}_3857.tif"
    colored = input_tif.parent / f"{input_tif.stem}_rgba.tif"
    ramp_file = input_tif.parent / f"{input_tif.stem}_ramp.txt"

    # Write color ramp file
    with open(ramp_file, "w") as f:
        f.write(COLOR_RAMP)

    # Step 1: Reproject to EPSG:3857
    print(f"    Reprojecting {input_tif.name} → EPSG:3857...")
    subprocess.run(
        [GDALWARP, "-t_srs", "EPSG:3857", "-r", "average",
         "-srcnodata", "-9999", "-dstnodata", "-9999",
         str(input_tif), str(warped)],
        check=True, capture_output=True,
    )

    # Step 2: Apply color relief
    print(f"    Applying color relief...")
    subprocess.run(
        [GDALDEM, "color-relief", "-alpha",
         str(warped), str(ramp_file), str(colored)],
        check=True, capture_output=True,
    )

    # Step 3: Generate XYZ tiles
    print(f"    Generating tiles → {tile_output_dir}")
    subprocess.run(
        ["/c/ProgramData/miniconda3/envs/irrigation_water/python.exe",
         "-m", "osgeo_utils.gdal2tiles",
         "--xyz",
         f"--zoom={zoom_range}",
         "--processes=4",
         "--resampling=average",
         str(colored), str(tile_output_dir)],
        check=True, capture_output=True,
    )

    # Clean up intermediate files
    for tmp in [warped, colored, ramp_file]:
        if tmp.exists():
            tmp.unlink()

    print(f"    Done: {tile_output_dir}")


def process_monthly(records: list[dict], source_dir: Path):
    """Group files by year-month, average, generate tiles, write monthly JSON."""
    # Group records by year-month
    groups = defaultdict(list)
    for r in records:
        ym = date_to_year_month(r["time"])
        groups[ym].append(r)

    print(f"\nPhase 2: Monthly aggregation — {len(groups)} months")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    TILES_DIR.mkdir(parents=True, exist_ok=True)

    monthly_records = []
    for ym in sorted(groups.keys()):
        recs = groups[ym]
        filepaths = [source_dir / r["file"] for r in recs]
        print(f"  {ym}: {len(recs)} 8-day files")

        # Average into monthly composite
        composite_path = TEMP_DIR / f"ssm_{ym}.tif"
        stats = average_rasters(filepaths, composite_path)
        monthly_records.append({
            "time": ym,
            "value": stats["mean"],
            "min": stats["min"],
            "max": stats["max"],
            "count": stats["count"],
        })

        # Generate tiles
        tile_dir = TILES_DIR / ym
        if stats["mean"] is not None:
            generate_tiles(composite_path, tile_dir)
        else:
            print(f"    Skipping tiles — no valid data for {ym}")

    # Write monthly JSON
    times_path = SERIES_DIR / "ssm_times.json"
    with open(times_path, "w", encoding="utf-8") as f:
        json.dump([r["time"] for r in monthly_records], f, ensure_ascii=False)
    print(f"Wrote {times_path} ({len(monthly_records)} entries)")

    series_path = SERIES_DIR / "ssm_series.json"
    with open(series_path, "w", encoding="utf-8") as f:
        json.dump([{"time": r["time"], "value": r["value"]} for r in monthly_records],
                  f, ensure_ascii=False)
    print(f"Wrote {series_path} ({len(monthly_records)} entries)")


# === Main ===

def main():
    print("=" * 60)
    print("  SSM Data Processing Script")
    print(f"  Source: {SOURCE_DIR}")
    print(f"  Output: {DATA_DIR}")
    print("=" * 60)

    # Phase 1: 8-day statistics
    print("\n--- Phase 1: 8-day Statistics ---")
    records = extract_8day_stats(SOURCE_DIR)
    write_8day_json(records)

    # Phase 2: Monthly aggregation & tiles
    print("\n--- Phase 2: Monthly Aggregation & Tiles ---")
    process_monthly(records, SOURCE_DIR)

    print("\n" + "=" * 60)
    print("  Processing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run Phase 1 (8-day stats) to verify output**

```bash
/c/ProgramData/miniconda3/envs/irrigation_water/python.exe scripts/process_ssm_data.py
```

Check: `data/series/ssm_8day_times.json` has ~181 entries, `data/series/ssm_8day_series.json` has valid float values.

- [ ] **Step 3: Verify generated JSON files**

```bash
python -c "
import json
with open('data/series/ssm_8day_times.json') as f: t = json.load(f)
print(f'8-day times: {len(t)} entries, {t[0]} to {t[-1]}')
with open('data/series/ssm_8day_series.json') as f: s = json.load(f)
print(f'8-day series: {len(s)} entries, first value: {s[0]}')
with open('data/series/ssm_times.json') as f: mt = json.load(f)
print(f'Monthly times: {len(mt)} entries, {mt[0]} to {mt[-1]}')
with open('data/series/ssm_series.json') as f: ms = json.load(f)
vals = [p['value'] for p in ms if p['value'] is not None]
print(f'Monthly series: {len(ms)} entries, values range {min(vals):.4f} to {max(vals):.4f}')
"
```

Expected: 8-day times ~181 entries from 2010-01-01 to 2013-12-27; monthly times 48 entries from 2010-01 to 2013-12.

- [ ] **Step 4: Commit**

```bash
git add scripts/process_ssm_data.py data/series/ssm_8day_times.json data/series/ssm_8day_series.json data/series/ssm_times.json data/series/ssm_series.json
git commit -m "feat: add SSM processing script and generated time series data"
```

---

### Task 2: Layer Registration & Validation Update

**Files:**
- Modify: `data/metadata/layers.json:37-72`
- Modify: `data/validate_data.py:131-168,185-243,412-441`

**Interfaces:**
- Produces: SSM layer definition visible to frontend via `/api/layers`
- Validation script accommodates non-12-size time series and dynamic layer list

- [ ] **Step 1: Add SSM layer to layers.json**

Add to the array in `data/metadata/layers.json` after the existing 4 layers:

```json
  {
    "id": "ssm",
    "name": "表层土壤水分",
    "description": "Surface Soil Moisture (0-5cm) from SSM prediction model, 8-day composite, 2010-2013",
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

- [ ] **Step 2: Update validate_data.py — dynamic layer discovery**

In `validate_times_files()` (line 131), replace the hardcoded layer list:

```python
# OLD (lines 131-135):
def validate_times_files():
    print("[2/5] Validating *_times.json files...")
    errors = []
    layer_ids = ["ndvi", "precipitation", "soil_moisture", "lst"]

# NEW:
def validate_times_files():
    print("[2/5] Validating *_times.json files...")
    errors = []

    # Discover layer IDs from layers.json
    layers, _ = load_json("data/metadata/layers.json")
    layer_ids = [la["id"] for la in layers] if isinstance(layers, list) else []
    if not layer_ids:
        return ["Cannot read layer IDs from layers.json"]

    # Collect expected time points from each layer's timeRange
    for lid in layer_ids:
        path = f"data/series/{lid}_times.json"
        data, err = load_json(path)
        if err:
            errors.append(err)
            continue

        if not isinstance(data, list):
            errors.append(f"{path}: must be a JSON array")
            continue

        # Remove hard 12-entry requirement; validate format and sort order
        seen = set()
        for i, entry in enumerate(data):
            if not isinstance(entry, str):
                errors.append(f"{path}[{i}]: must be a string, got {type(entry).__name__}")
                continue
            if not re.match(r"^\d{4}-\d{2}$", entry):
                errors.append(f"{path}[{i}]: '{entry}' must match YYYY-MM")
            if entry in seen:
                errors.append(f"{path}[{i}]: duplicate time '{entry}'")
            seen.add(entry)

        if all(isinstance(e, str) and re.match(r"^\d{4}-\d{2}$", e) for e in data):
            sorted_data = sorted(data)
            if data != sorted_data:
                errors.append(f"{path}: entries must be chronologically sorted")

    print(f"  >> {len(layer_ids)} files checked, {len(errors)} errors")
    return errors
```

- [ ] **Step 3: Update validate_series_files() — dynamic layer list, remove count constraint**

In `validate_series_files()` (line 185), same pattern:

```python
# OLD (lines 185-189):
def validate_series_files():
    print("[3/5] Validating *_series.json files...")
    errors = []
    layer_ids = ["ndvi", "precipitation", "soil_moisture", "lst"]

# NEW:
def validate_series_files():
    print("[3/5] Validating *_series.json files...")
    errors = []

    # Discover layer IDs from layers.json
    layers, _ = load_json("data/metadata/layers.json")
    layer_ids = [la["id"] for la in layers] if isinstance(layers, list) else []
    if not layer_ids:
        return ["Cannot read layer IDs from layers.json"]

    ranges = get_layer_ranges()

    for lid in layer_ids:
        path = f"data/series/{lid}_series.json"
        data, err = load_json(path)
        if err:
            errors.append(err)
            continue

        if not isinstance(data, list):
            errors.append(f"{path}: must be a JSON array")
            continue
        # Remove hard 12-entry check

        # (rest of existing validation logic unchanged from line 205 onward)
        seen_times = set()
        for i, point in enumerate(data):
            # ... keep existing validation code ...
```

And similarly update `validate_times_series_consistency()` (line 412):

```python
# OLD (lines 412-417):
def validate_times_series_consistency():
    print("[5/5] Validating time-series consistency...")
    errors = []
    layer_ids = ["ndvi", "precipitation", "soil_moisture", "lst"]

# NEW:
def validate_times_series_consistency():
    print("[5/5] Validating time-series consistency...")
    errors = []

    layers, _ = load_json("data/metadata/layers.json")
    layer_ids = [la["id"] for la in layers] if isinstance(layers, list) else []
    if not layer_ids:
        return ["Cannot read layer IDs from layers.json"]
```

- [ ] **Step 4: Run validation script**

```bash
python data/validate_data.py
```

Expected: PASS with 5 layers checked.

- [ ] **Step 5: Commit**

```bash
git add data/metadata/layers.json data/validate_data.py
git commit -m "feat: add SSM layer definition, make validation dynamic"
```

---

### Task 3: Backend — 8-day Resolution API Support

**Files:**
- Modify: `backend/data_loader.py:34-42`
- Modify: `backend/routers/series.py:10-51`
- Modify: `backend/routers/layers.py:16-31`

**Interfaces:**
- `get_layer_times(layer_id, resolution='month')` — new `resolution` param
- `get_series(layer_id, resolution='month')` — new `resolution` param
- `GET /api/layers/{layer_id}/times?resolution=8day` — new query param
- `GET /api/series?layerId=ssm&resolution=8day` — new query param
- Consumes: `ssm_8day_times.json`, `ssm_8day_series.json`
- Produces: 8-day time points and series values for frontend charts

- [ ] **Step 1: Write failing test for data_loader resolution support**

Create `backend/tests/test_ssm_data.py`:

```python
"""Tests for SSM 8-day data loading."""
import json
import os
import tempfile
from pathlib import Path

import pytest


# We'll test the data_loader functions directly
def test_get_layer_times_8day_resolution():
    """get_layer_times with resolution='8day' should load 8-day times file."""
    # Set up mock project root
    import backend.data_loader as dl

    original_root = dl.PROJECT_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        dl.PROJECT_ROOT = Path(tmp)

        # Create data directory structure
        (Path(tmp) / "data" / "series").mkdir(parents=True)
        (Path(tmp) / "data" / "metadata").mkdir(parents=True)

        # Write test layers.json
        with open(Path(tmp) / "data" / "metadata" / "layers.json", "w") as f:
            json.dump([{
                "id": "ssm", "name": "SSM", "type": "soil", "unit": "m³/m³",
                "range": {"min": 0, "max": 1},
                "timeRange": {"start": "2010-01", "end": "2010-12", "step": "month"},
                "tileTemplate": "data/tiles/ssm/{time}/{z}/{x}/{y}.png",
                "legend": [{"color": "#ff0000", "label": "dry"}]
            }], f)

        # Write test 8-day times
        times = ["2010-01-01", "2010-01-09", "2010-01-17"]
        with open(Path(tmp) / "data" / "series" / "ssm_8day_times.json", "w") as f:
            json.dump(times, f)

        # Test 8-day resolution
        result = dl.get_layer_times("ssm", resolution="8day")
        assert result == times

        # Clean up
        dl.PROJECT_ROOT = original_root


def test_get_series_8day_resolution():
    """get_series with resolution='8day' should load 8-day series file."""
    import backend.data_loader as dl

    original_root = dl.PROJECT_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        dl.PROJECT_ROOT = Path(tmp)
        (Path(tmp) / "data" / "series").mkdir(parents=True)
        (Path(tmp) / "data" / "metadata").mkdir(parents=True)

        with open(Path(tmp) / "data" / "metadata" / "layers.json", "w") as f:
            json.dump([{
                "id": "ssm", "name": "SSM", "type": "soil", "unit": "m³/m³",
                "range": {"min": 0, "max": 1},
                "timeRange": {"start": "2010-01", "end": "2010-12", "step": "month"},
                "tileTemplate": "data/tiles/ssm/{time}/{z}/{x}/{y}.png",
                "legend": [{"color": "#ff0000", "label": "dry"}]
            }], f)

        series = [
            {"time": "2010-01-01", "value": 0.15},
            {"time": "2010-01-09", "value": 0.18},
            {"time": "2010-01-17", "value": 0.22},
        ]
        with open(Path(tmp) / "data" / "series" / "ssm_8day_series.json", "w") as f:
            json.dump(series, f)

        result = dl.get_series("ssm", resolution="8day")
        assert result == series

        dl.PROJECT_ROOT = original_root
```

- [ ] **Step 2: Run tests — should fail**

```bash
cd frontend && npx vitest run --reporter=verbose 2>&1 | tail -5
```

Expected: test failures because `resolution` parameter doesn't exist yet.

- [ ] **Step 3: Implement resolution support in data_loader.py**

Modify `backend/data_loader.py`:

```python
# Replace get_layer_times (line 34):
def get_layer_times(layer_id: str, resolution: str = "month") -> list[str]:
    """Return the time points for a given layer.

    Args:
        layer_id: Layer identifier (e.g. 'ssm').
        resolution: 'month' (default) or '8day'.
    """
    if resolution == "8day":
        return _load_json(f"data/series/{layer_id}_8day_times.json")
    return _load_json(f"data/series/{layer_id}_times.json")


# Replace get_series (line 39):
def get_series(layer_id: str, resolution: str = "month") -> list[dict]:
    """Return the time series data for a given layer.

    Args:
        layer_id: Layer identifier (e.g. 'ssm').
        resolution: 'month' (default) or '8day'.
    """
    if resolution == "8day":
        return _load_json(f"data/series/{layer_id}_8day_series.json")
    return _load_json(f"data/series/{layer_id}_series.json")
```

Also update `get_region_series` to pass resolution through:

```python
def get_region_series(layer_id: str, region_id: str | None = None, resolution: str = "month") -> list[dict]:
    """Return time series data for a layer, optionally filtered by region."""
    if region_id:
        region_data = _load_json("data/series/region_series.json")
        if region_id in region_data and layer_id in region_data[region_id]:
            return region_data[region_id][layer_id]

    return _load_json(f"data/series/{layer_id}_{'8day_' if resolution == '8day' else ''}series.json")
```

- [ ] **Step 4: Add resolution param to routers/layers.py**

Modify `backend/routers/layers.py`:

```python
@router.get("/layers/{layer_id}/times")
def layer_times(layer_id: str, resolution: str = "month"):
    """Return available time points for a given layer.

    Query params:
        resolution: 'month' (default) or '8day' for 8-day composite data.
    """
    layer = get_layer(layer_id)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layer_id}' not found",
        )
    try:
        return get_layer_times(layer_id, resolution=resolution)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time data for layer '{layer_id}' not found",
        )
```

- [ ] **Step 5: Add resolution param to routers/series.py**

Modify `backend/routers/series.py`:

```python
@router.get("/series")
def list_series(
    layerId: str = Query(...),
    regionId: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    resolution: str = Query(default="month"),
):
    """Return time series data for a layer and optionally a region.

    Query params:
        resolution: 'month' (default) or '8day'.
    """
    layer = get_layer(layerId)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layerId}' not found",
        )

    try:
        data = get_region_series(layerId, regionId, resolution=resolution)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Series data for layer '{layerId}' not found",
        )

    if start or end:
        filtered = []
        for entry in data:
            t = entry["time"]
            if start and t < start:
                continue
            if end and t > end:
                continue
            filtered.append(entry)
        return filtered

    return data
```

- [ ] **Step 6: Run backend tests**

```bash
PYTHONPATH=. python -m pytest backend/tests/test_ssm_data.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 7: Run all backend tests**

```bash
PYTHONPATH=. python -m pytest backend/tests/ -v
```

Expected: all existing tests pass + new SSM tests.

- [ ] **Step 8: Commit**

```bash
git add backend/data_loader.py backend/routers/layers.py backend/routers/series.py backend/tests/test_ssm_data.py
git commit -m "feat: add resolution query param for 8-day data support"
```

---

### Task 4: Frontend — Chart and Time Label Improvements

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx:19-23`
- Modify: `frontend/src/components/ChartPanel.tsx:1-167`

**Interfaces:**
- Produces: Proper time formatting for YYYY-MM-DD (8-day) and YYYY-MM (monthly) labels
- ChartPanel renders correct labels for both resolutions

- [ ] **Step 1: Update formatTime in Sidebar.tsx**

Replace the `formatTime` function to handle both `YYYY-MM` and `YYYY-MM-DD` formats:

```tsx
function formatTime(t: string): string {
  // e.g. "2025-06" → "2025年06月"
  // e.g. "2010-01-01" → "2010年01月01日"
  const parts = t.split('-')
  if (parts.length === 3) {
    return `${parts[0]}年${parts[1]}月${parts[2]}日`
  }
  if (parts.length === 2) {
    return `${parts[0]}年${parts[1]}月`
  }
  return t
}
```

- [ ] **Step 2: Verify frontend compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: support YYYY-MM-DD time labels in sidebar"
```

---

### Task 5: End-to-End Verification

**Files:** None (verification only).

- [ ] **Step 1: Kill and restart backend**

```bash
# Kill old backend
taskkill //F //PID $(cat /tmp/backend.pid 2>/dev/null) 2>/dev/null; echo "old backend stopped"
# Start fresh
cd E:/遥感数据展示网站 && PYTHONPATH=. python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
```

- [ ] **Step 2: Verify API endpoints**

```bash
# Check layers include SSM
curl -s http://localhost:8000/api/layers | python -c "import json,sys; d=json.load(sys.stdin); print([l['id'] for l in d])"
# Expected: ['ndvi', 'precipitation', 'soil_moisture', 'lst', 'ssm']

# Check monthly times
curl -s "http://localhost:8000/api/layers/ssm/times" | python -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} monthly times: {d[0]} to {d[-1]}')"

# Check 8-day times
curl -s "http://localhost:8000/api/layers/ssm/times?resolution=8day" | python -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} 8-day times: {d[0]} to {d[-1]}')"

# Check monthly series
curl -s "http://localhost:8000/api/series?layerId=ssm" | python -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} monthly series points')"

# Check 8-day series
curl -s "http://localhost:8000/api/series?layerId=ssm&resolution=8day" | python -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} 8-day series points')"

# Check a tile exists
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/data/tiles/ssm/2010-06/0/0/0.png"
```

Expected: SSM layer visible, monthly and 8-day endpoints work, tiles return 200 or 404 (depending on data coverage at zoom 0).

- [ ] **Step 3: Launch frontend and open browser**

Visit `http://localhost:5173` in browser, verify:
- SSM layer appears in layer selector
- Selecting SSM shows tiles on the map (if tiles generated for that month)
- Chart shows the time series
- Time slider navigates through monthly time points

- [ ] **Step 4: Commit final verification notes**

```bash
git add -A
git commit -m "chore: end-to-end verification of SSM data integration"
```
