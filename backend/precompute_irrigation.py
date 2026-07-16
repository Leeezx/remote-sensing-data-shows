"""Precompute irrigation water statistics for administrative regions.

Reads the configured shapefiles, computes annual and monthly
irrigation water totals for every feature, and writes the results to
data/stats/irrigation_region_series.json so the /irrigation/series
endpoint returns precomputed data without touching raster files.

Usage:
    python backend/precompute_irrigation.py                          # all counties
    python backend/precompute_irrigation.py --limit 10               # first 10 only
    python backend/precompute_irrigation.py --level township         # all townships
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Allow importing from the project root without installing the package
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.irrigation_stats import _annual_series, _monthly_series  # noqa: E402
from backend.shapefile_geojson import read_shapefile_geojson  # noqa: E402

COUNTY_SHAPEFILE = Path(r"F:\矢量底图\中国_县\中国_县.shp")
TOWNSHIP_SHAPEFILE = Path(r"F:\矢量底图\中国_乡镇\乡镇街道\乡镇街道.shp")
OUTPUT_PATH = PROJECT_ROOT / "data" / "stats" / "irrigation_region_series.json"
REGIONS_PATH = PROJECT_ROOT / "data" / "stats" / "irrigation_regions.json"

# Shapefile by level
_LEVEL_SHAPEFILES: dict[str, Path] = {
    "county": COUNTY_SHAPEFILE,
    "township": TOWNSHIP_SHAPEFILE,
}
_CHECKPOINT_INTERVAL = 20


def _checkpoint_path(path: Path) -> Path:
    """Return the sidecar path used when the main output is locked."""
    return path.with_name(f"{path.name}.checkpoint")


def _load_json_with_checkpoint(path: Path) -> dict:
    """Load the newest valid output or sidecar checkpoint."""
    candidates = [
        candidate
        for candidate in (path, _checkpoint_path(path))
        if candidate.is_file()
    ]
    candidates.sort(key=lambda candidate: candidate.stat().st_mtime_ns, reverse=True)
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if candidate != path:
                print(f"Resuming from checkpoint: {candidate}")
            return payload
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def _write_json(path: Path, payload: object) -> None:
    """Write JSON through a same-directory temporary file and replace atomically.

    Replacing a completed temporary file avoids truncating the existing large
    output in place, which is fragile on Windows when the file is being read by
    another process. If the target remains locked, retain the completed write
    as a sidecar checkpoint for the next run.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        replace_error: OSError | None = None
        for attempt in range(3):
            try:
                os.replace(temp_path, path)
                temp_path = None
                replace_error = None
                break
            except OSError as exc:
                if not isinstance(exc, PermissionError) and exc.errno not in (13, 22):
                    raise
                replace_error = exc
                if attempt < 2:
                    time.sleep(0.5)

        if replace_error is not None:
            checkpoint = _checkpoint_path(path)
            os.replace(temp_path, checkpoint)
            temp_path = None
            print(
                f"WARNING: {path} is locked; checkpoint saved to {checkpoint}. "
                "Close the process reading the output file to publish it."
            )
        else:
            checkpoint = _checkpoint_path(path)
            if checkpoint.is_file():
                try:
                    checkpoint.unlink()
                except PermissionError:
                    pass
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def build_region_catalog(
    series_data: dict,
    previous_regions: list[dict] | None = None,
) -> list[dict]:
    """Build a stable county+township catalog from merged series data."""
    previous_by_key = {
        (str(region.get("level", "")), str(region.get("id", ""))): region
        for region in (previous_regions or [])
        if isinstance(region, dict)
    }
    catalog: list[dict] = []
    for level in ("county", "township"):
        level_data = series_data.get(level, {})
        if not isinstance(level_data, dict):
            continue
        for region_id in sorted(str(key) for key in level_data):
            entry = level_data.get(region_id)
            if not isinstance(entry, dict):
                continue
            previous = previous_by_key.get((level, region_id), {})
            catalog.append({
                "id": region_id,
                "name": str(entry.get("name") or region_id),
                "level": level,
                "parentId": previous.get("parentId"),
            })
    return catalog


def _load_previous_regions() -> list[dict]:
    if not REGIONS_PATH.is_file():
        return []
    try:
        payload = json.loads(REGIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _publish_region_catalog(series_data: dict) -> list[dict]:
    previous = _load_previous_regions()
    catalog = build_region_catalog(series_data, previous)
    if catalog != previous:
        _write_json(REGIONS_PATH, catalog)
    return catalog


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
        choices=["county", "township"],
        default="county",
        help="Administrative level to precompute (default: county)",
    )
    parser.add_argument(
        "--parent-shp",
        type=Path,
        default=None,
        help="Deprecated and ignored; retained for command-line compatibility",
    )
    parser.add_argument(
        "--regions-only",
        action="store_true",
        help="Rebuild irrigation_regions.json from existing series without reading shapefiles",
    )
    args = parser.parse_args()

    # Load or initialize the output file so we can resume interrupted runs
    existing: dict = {"unit": "万m³", "county": {}, "township": {}}
    if OUTPUT_PATH.is_file() or _checkpoint_path(OUTPUT_PATH).is_file():
        try:
            loaded = _load_json_with_checkpoint(OUTPUT_PATH)
            if loaded:
                existing = loaded
        except (OSError, json.JSONDecodeError):
            pass

    if args.regions_only:
        catalog = _publish_region_catalog(existing)
        print(f"Published {len(catalog)} regions to {REGIONS_PATH}")
        return

    shp = _LEVEL_SHAPEFILES.get(args.level)
    if shp is None or not shp.is_file():
        print(f"ERROR: Shapefile not found for level '{args.level}': {shp}")
        sys.exit(1)

    if args.parent_shp:
        print("Parent shapefile argument ignored; spatial filtering is disabled")

    print(f"Reading shapefile: {shp}")
    t0 = time.time()
    geojson = read_shapefile_geojson(shp)
    features = geojson.get("features", [])
    print(f"Loaded {len(features)} features in {time.time() - t0:.1f}s")

    if args.limit:
        features = features[: args.limit]
        print(f"Limited to first {len(features)} features")

    already = sum(
        1
        for r in existing.get(args.level, {}).values()
        if isinstance(r, dict) and r.get("annual") and r.get("monthly")
    )
    print(f"Resuming from existing output ({already} regions already complete)")

    level = args.level
    level_data = existing.setdefault(level, {})
    skipped = 0
    errors = 0
    dirty = False
    checkpoint_dirty = False
    total_start = time.time()

    for i, feature in enumerate(features):
        props = feature.get("properties", {})
        region_id = str(
            props.get("gb")
            or props.get("GB")
            or props.get("id")
            or props.get("code")
            or ""
        )
        region_name = str(
            props.get("name")
            or props.get("NAME")
            or props.get("Name")
            or region_id
        )

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

        entry = level_data.get(region_id)
        if entry is None:
            entry = {"name": region_name, "annual": None, "monthly": None}
            level_data[region_id] = entry
            dirty = True
            checkpoint_dirty = True
        elif entry.get("name") != region_name:
            entry["name"] = region_name
            dirty = True
            checkpoint_dirty = True

        # Annual series -------------------------------------------------
        if entry.get("annual") is None:
            label = f"[{i + 1}/{len(features)}] {region_name}"
            print(f"{label}: computing annual series ... ", end="", flush=True)
            t_annual = time.time()
            try:
                entry["annual"] = _annual_series(geometry)
                dirty = True
                checkpoint_dirty = True
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
                dirty = True
                checkpoint_dirty = True
                elapsed = time.time() - t_monthly
                print(f"{len(entry['monthly'])} points ({elapsed:.1f}s)")
            except Exception as exc:
                errors += 1
                print(f"ERROR: {exc}")

        # Checkpoint periodically so interrupted runs can resume without
        # rewriting the large output file after every region.
        if checkpoint_dirty and (i + 1) % _CHECKPOINT_INTERVAL == 0:
            _write_json(OUTPUT_PATH, existing)
            checkpoint_dirty = False

        if (i + 1) % _CHECKPOINT_INTERVAL == 0:
            elapsed = time.time() - total_start
            rate = (i + 1 - skipped) / max(elapsed, 0.1)
            remaining = (len(features) - i - 1) / max(rate, 0.01)
            print(
                f"  [progress] {i + 1}/{len(features)} regions, "
                f"{rate:.2f} regions/s, ~{remaining:.0f}s remaining"
            )

    # Always save the final series, including when the feature count is not
    # an exact multiple of the checkpoint interval.
    if dirty:
        _write_json(OUTPUT_PATH, existing)

    # Write updated region list -----------------------------------------
    _publish_region_catalog(existing)

    total_elapsed = time.time() - total_start
    completed = len(features) - skipped
    print()
    print(f"Done in {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)")
    print(f"  Regions: {completed} completed, {skipped} skipped, {errors} errors")
    print(f"  Output:  {OUTPUT_PATH}")
    print(f"  Regions: {REGIONS_PATH}")


if __name__ == "__main__":
    main()
