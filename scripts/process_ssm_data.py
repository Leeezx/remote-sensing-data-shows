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
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio

# === Configuration ===
SOURCE_DIR = Path("F:/全国灌溉用水反演/数据2010-2013/SSM预测结果")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SERIES_DIR = DATA_DIR / "series"
TILES_DIR = DATA_DIR / "tiles" / "ssm"
TEMP_DIR = PROJECT_ROOT / "temp_ssm"

# GDAL executables (Windows paths required for subprocess)
GDALWARP = r"C:\ProgramData\miniconda3\Library\bin\gdalwarp.exe"
GDALDEM = r"C:\ProgramData\miniconda3\Library\bin\gdaldem.exe"
GDAL2TILES_PYTHON = r"C:\ProgramData\miniconda3\envs\irrigation_water\python.exe"

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
        json.dump(times, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {times_path} ({len(times)} entries)")

    # Series file
    series = [{"time": r["time"], "value": r["value"], "min": r["min"], "max": r["max"], "count": r["count"]} for r in records]
    series_path = SERIES_DIR / "ssm_8day_series.json"
    with open(series_path, "w", encoding="utf-8") as f:
        json.dump(series, f, ensure_ascii=False, indent=2)
        f.write("\n")
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
         "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=2", "-co", "TILED=YES",
         "-tr", "500", "500",
         str(input_tif), str(warped)],
        check=True, capture_output=True,
    )

    # Step 2: Apply color relief
    print(f"    Applying color relief...")
    subprocess.run(
        [GDALDEM, "color-relief", "-alpha",
         "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=2", "-co", "TILED=YES",
         str(warped), str(ramp_file), str(colored)],
        check=True, capture_output=True,
    )

    # Step 3: Generate XYZ tiles
    print(f"    Generating tiles → {tile_output_dir}")
    subprocess.run(
        [GDAL2TILES_PYTHON,
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


def process_monthly(records: list[dict], source_dir: Path, skip_tiles: bool = False):
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
        if not skip_tiles:
            tile_dir = TILES_DIR / ym
            if stats["mean"] is not None:
                generate_tiles(composite_path, tile_dir)
            else:
                print(f"    Skipping tiles — no valid data for {ym}")
        else:
            print(f"    Tiles skipped (--skip-tiles flag)")

    # Write monthly JSON
    times_path = SERIES_DIR / "ssm_times.json"
    with open(times_path, "w", encoding="utf-8") as f:
        json.dump([r["time"] for r in monthly_records], f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {times_path} ({len(monthly_records)} entries)")

    series_path = SERIES_DIR / "ssm_series.json"
    with open(series_path, "w", encoding="utf-8") as f:
        json.dump([{"time": r["time"], "value": r["value"], "min": r["min"], "max": r["max"], "count": r["count"]} for r in monthly_records],
                  f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {series_path} ({len(monthly_records)} entries)")


# === Main ===

def main():
    skip_tiles = "--skip-tiles" in sys.argv

    print("=" * 60)
    print("  SSM Data Processing Script")
    print(f"  Source: {SOURCE_DIR}")
    print(f"  Output: {DATA_DIR}")
    if skip_tiles:
        print("  [Tile generation SKIPPED]")
    print("=" * 60)

    # Phase 1: 8-day statistics
    print("\n--- Phase 1: 8-day Statistics ---")
    records = extract_8day_stats(SOURCE_DIR)
    write_8day_json(records)

    # Phase 2: Monthly aggregation & tiles
    print("\n--- Phase 2: Monthly Aggregation & Tiles ---")
    process_monthly(records, SOURCE_DIR, skip_tiles=skip_tiles)

    print("\n" + "=" * 60)
    print("  Processing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
