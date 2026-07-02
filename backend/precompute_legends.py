"""Precompute irrigation legend thresholds for all time points and cache to disk.

Reads every available irrigation raster (annual + monthly), computes
data-driven legend thresholds, and writes them all to
data/stats/irrigation_legends.json so the /irrigation/legend endpoint
and tile renderer can serve legends instantly without opening rasters.

Usage:
    python backend/precompute_legends.py
"""

import json
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows terminals
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.data_loader import (  # noqa: E402
    IRRIGATION_8DAY_ROOT,
    IRRIGATION_ANNUAL_ROOT,
    IRRIGATION_ANNUAL_COG_ROOT,
    IRRIGATION_8DAY_COG_ROOT,
    get_irrigation_layer,
    get_irrigation_times,
)
from backend.irrigation_legend import (  # noqa: E402
    _save_legend_disk_cache,
    build_irrigation_dynamic_legend,
)
from backend.irrigation_time import irrigation_time_to_cog_path  # noqa: E402


def compute_legend_for_time(time_str: str) -> list[dict]:
    """Compute percentiles for one time point and return legend items."""
    raster_path = irrigation_time_to_cog_path(
        IRRIGATION_ANNUAL_ROOT,
        IRRIGATION_ANNUAL_COG_ROOT,
        IRRIGATION_8DAY_ROOT,
        IRRIGATION_8DAY_COG_ROOT,
        time_str,
    )
    if not raster_path.is_file():
        print(f"  raster not found: {raster_path}")
        return []

    import numpy as np
    import rasterio

    with rasterio.open(raster_path) as ds:
        values = ds.read(1)
        source_mask = ds.read_masks(1)
        nodata = ds.nodata

    layer = get_irrigation_layer()
    legend = build_irrigation_dynamic_legend(
        values,
        layer["legend"],
        layer["unit"],
        source_mask=source_mask,
        nodata=nodata,
    )
    return legend


def main() -> None:
    layer = get_irrigation_layer()
    print(f"图层: {layer['name']} ({layer['unit']})")
    print()

    # Collect all time points
    times: list[str] = []
    times.extend(get_irrigation_times("annual"))
    times.extend(get_irrigation_times("month"))
    total = len(times)
    print(f"共 {total} 个时间点 ({len(get_irrigation_times('annual'))} 年度 + {len(get_irrigation_times('month'))} 月度)")
    print()

    # Load existing cache
    cache_path = PROJECT_ROOT / "data" / "stats" / "irrigation_legends.json"
    disk_cache: dict = {}
    if cache_path.is_file():
        try:
            disk_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            existing = sum(1 for t in times if t in disk_cache)
            print(f"已有 {existing}/{total} 个预计算图例")
        except (OSError, json.JSONDecodeError):
            pass

    computed = 0
    skipped = 0
    t_start = time.time()

    for i, time_str in enumerate(times):
        if time_str in disk_cache:
            skipped += 1
            continue

        label = f"[{i+1:4d}/{total}] {time_str}"
        print(f"{label}: computing ... ", end="", flush=True)
        t0 = time.time()
        try:
            legend = compute_legend_for_time(time_str)
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue

        if not legend:
            print("empty raster, skipped")
            skipped += 1
            continue

        disk_cache[time_str] = legend
        computed += 1
        elapsed = time.time() - t0
        print(f"{elapsed:.1f}s")

        # Save incrementally
        _save_legend_disk_cache(disk_cache)

        if computed % 10 == 0:
            total_elapsed = time.time() - t_start
            rate = (computed + skipped) / max(total_elapsed, 0.1)
            remaining = (total - i - 1) / max(rate, 0.01)
            print(f"  [progress] {i+1}/{total}, ~{remaining:.0f}s remaining")

    total_time = time.time() - t_start
    print()
    print(f"完成! 耗时 {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  新计算: {computed}")
    print(f"  跳过:   {skipped}")
    print(f"  缓存:   {cache_path} ({len(disk_cache)} entries)")


if __name__ == "__main__":
    main()
