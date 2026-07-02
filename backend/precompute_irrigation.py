"""Precompute irrigation water statistics for all counties and save to JSON.

Reads the configured county shapefile, computes annual and monthly
irrigation water totals for every feature, and writes the results to
data/stats/irrigation_region_series.json so the /irrigation/series
endpoint returns precomputed data without touching raster files.

Usage:
    python backend/precompute_irrigation.py              # all counties
    python backend/precompute_irrigation.py --limit 10   # first 10 only
    python backend/precompute_irrigation.py --limit 10 --level county
"""

import json
import sys
import time
from pathlib import Path

# Allow importing from the project root without installing the package
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.irrigation_stats import _annual_series, _monthly_series  # noqa: E402
from backend.shapefile_geojson import read_shapefile_geojson  # noqa: E402

COUNTY_SHAPEFILE = Path(r"F:\矢量底图\中国_县\中国_县.shp")
OUTPUT_PATH = PROJECT_ROOT / "data" / "stats" / "irrigation_region_series.json"
REGIONS_PATH = PROJECT_ROOT / "data" / "stats" / "irrigation_regions.json"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Precompute irrigation water statistics for administrative regions"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Process only the first N regions"
    )
    parser.add_argument(
        "--level",
        choices=["county", "village"],
        default="county",
        help="Administrative level to precompute (default: county)",
    )
    args = parser.parse_args()

    shp = COUNTY_SHAPEFILE
    if not shp.is_file():
        print(f"ERROR: Shapefile not found: {shp}")
        sys.exit(1)

    print(f"Reading shapefile: {shp}")
    t0 = time.time()
    geojson = read_shapefile_geojson(shp)
    features = geojson.get("features", [])
    print(f"Loaded {len(features)} features in {time.time() - t0:.1f}s")

    if args.limit:
        features = features[: args.limit]
        print(f"Limited to first {len(features)} features")

    # Load or initialize the output file so we can resume interrupted runs
    existing: dict = {"unit": "万m³", "county": {}, "village": {}}
    if OUTPUT_PATH.is_file():
        try:
            existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            already = sum(
                1
                for r in existing.get(args.level, {}).values()
                if isinstance(r, dict) and r.get("annual") and r.get("monthly")
            )
            print(
                f"Resuming from existing output ({already} regions already complete)"
            )
        except (OSError, json.JSONDecodeError):
            pass

    level = args.level
    level_data = existing.setdefault(level, {})
    skipped = 0
    errors = 0
    total_start = time.time()

    for i, feature in enumerate(features):
        props = feature.get("properties", {})
        region_id = str(
            props.get("gb") or props.get("GB") or props.get("id") or ""
        )
        region_name = str(props.get("name") or props.get("NAME") or region_id)

        if not region_id:
            skipped += 1
            continue

        geometry = feature.get("geometry")
        if not geometry:
            print(
                f"[{i + 1}/{len(features)}] {region_name}: no geometry, skipping"
            )
            skipped += 1
            continue

        entry = level_data.setdefault(
            region_id, {"name": region_name, "annual": None, "monthly": None}
        )
        entry["name"] = region_name

        # Annual series -------------------------------------------------
        if entry.get("annual") is None:
            label = f"[{i + 1}/{len(features)}] {region_name}"
            print(f"{label}: computing annual series ... ", end="", flush=True)
            t_annual = time.time()
            try:
                entry["annual"] = _annual_series(geometry)
                elapsed = time.time() - t_annual
                print(f"{len(entry['annual'])} points ({elapsed:.1f}s)")
            except Exception as exc:
                errors += 1
                print(f"ERROR: {exc}")

        # Monthly series ------------------------------------------------
        if entry.get("monthly") is None:
            label = f"[{i + 1}/{len(features)}] {region_name}"
            print(f"{label}: computing monthly series ... ", end="", flush=True)
            t_monthly = time.time()
            try:
                entry["monthly"] = _monthly_series(geometry)
                elapsed = time.time() - t_monthly
                print(f"{len(entry['monthly'])} points ({elapsed:.1f}s)")
            except Exception as exc:
                errors += 1
                print(f"ERROR: {exc}")

        # Save after every region so interrupted runs can resume
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if (i + 1) % 20 == 0:
            elapsed = time.time() - total_start
            rate = (i + 1 - skipped) / max(elapsed, 0.1)
            remaining = (len(features) - i - 1) / max(rate, 0.01)
            print(
                f"  [progress] {i + 1}/{len(features)} regions, "
                f"{rate:.2f} regions/s, ~{remaining:.0f}s remaining"
            )

    # Write updated region list -----------------------------------------
    regions = []
    for rid, data in level_data.items():
        regions.append(
            {
                "id": rid,
                "name": data.get("name", rid),
                "level": level,
                "parentId": None,
            }
        )
    REGIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGIONS_PATH.write_text(
        json.dumps(regions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_elapsed = time.time() - total_start
    completed = len(features) - skipped
    print()
    print(f"Done in {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)")
    print(f"  Regions: {completed} completed, {skipped} skipped, {errors} errors")
    print(f"  Output:  {OUTPUT_PATH}")
    print(f"  Regions: {REGIONS_PATH}")


if __name__ == "__main__":
    main()
