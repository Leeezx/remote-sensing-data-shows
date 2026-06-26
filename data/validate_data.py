#!/usr/bin/env python3
"""
Data validation script for the Remote Sensing Data Display Website.

Verifies that all sample data files are well-formed and contain
realistic values within expected ranges. Run with:

    python data/validate_data.py

Exits with code 0 if all checks pass, code 1 if any fail.
"""

import json
import os
import re
import sys

# Paths relative to this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)


def load_json(rel_path):
    """Load and parse a JSON file, returning (data, error_msg)."""
    full_path = os.path.join(PROJECT_ROOT, rel_path) if not os.path.isabs(rel_path) else rel_path
    if not os.path.isfile(full_path):
        return None, f"File not found: {full_path}"
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON in {full_path}: {e}"
    except Exception as e:
        return None, f"Error reading {full_path}: {e}"


def validate_layers():
    """Validate layers.json."""
    print("[1/5] Validating layers.json...")
    layers, err = load_json("data/metadata/layers.json")
    if err:
        return [err]

    errors = []
    if not isinstance(layers, list):
        errors.append("layers.json must be a JSON array")
        return errors
    if len(layers) < 4:
        errors.append(f"Expected at least 4 layers, found {len(layers)}")

    layer_ids = set()
    valid_types = {"vegetation", "climate", "soil", "temperature"}

    for i, layer in enumerate(layers):
        prefix = f"Layer [{i}]"

        # Required string fields
        for field in ["id", "name", "type", "unit", "tileTemplate"]:
            if field not in layer:
                errors.append(f"{prefix}: missing required field '{field}'")
            elif not isinstance(layer[field], str):
                errors.append(f"{prefix}: '{field}' must be a string")
            elif not layer[field].strip():
                errors.append(f"{prefix}: '{field}' must not be empty")

        # id uniqueness and format
        if "id" in layer and isinstance(layer["id"], str):
            lid = layer["id"]
            if not re.match(r"^[a-z][a-z0-9_]*$", lid):
                errors.append(f"{prefix}: id '{lid}' must match ^[a-z][a-z0-9_]*$")
            if lid in layer_ids:
                errors.append(f"{prefix}: duplicate id '{lid}'")
            layer_ids.add(lid)

        # type validation
        if "type" in layer and layer["type"] not in valid_types:
            errors.append(f"{prefix}: type '{layer['type']}' not in {valid_types}")

        # range
        if "range" not in layer:
            errors.append(f"{prefix}: missing required field 'range'")
        elif isinstance(layer["range"], dict):
            r = layer["range"]
            for rk in ["min", "max"]:
                if rk not in r:
                    errors.append(f"{prefix}: range missing '{rk}'")
                elif not isinstance(r[rk], (int, float)):
                    errors.append(f"{prefix}: range.{rk} must be a number")
            if "min" in r and "max" in r and isinstance(r["min"], (int, float)) and isinstance(r["max"], (int, float)):
                if r["min"] >= r["max"]:
                    errors.append(f"{prefix}: range.min ({r['min']}) must be < range.max ({r['max']})")

        # timeRange
        if "timeRange" not in layer:
            errors.append(f"{prefix}: missing required field 'timeRange'")
        elif isinstance(layer["timeRange"], dict):
            tr = layer["timeRange"]
            for trk in ["start", "end", "step"]:
                if trk not in tr:
                    errors.append(f"{prefix}: timeRange missing '{trk}'")
            if "start" in tr and not re.match(r"^\d{4}-\d{2}$", str(tr["start"])):
                errors.append(f"{prefix}: timeRange.start '{tr['start']}' must be YYYY-MM")
            if "end" in tr and not re.match(r"^\d{4}-\d{2}$", str(tr["end"])):
                errors.append(f"{prefix}: timeRange.end '{tr['end']}' must be YYYY-MM")
            if "step" in tr and tr["step"] != "month":
                errors.append(f"{prefix}: timeRange.step must be 'month', got '{tr['step']}'")

        # legend
        if "legend" not in layer:
            errors.append(f"{prefix}: missing required field 'legend'")
        elif isinstance(layer["legend"], list):
            if len(layer["legend"]) < 3:
                errors.append(f"{prefix}: legend needs at least 3 entries, found {len(layer['legend'])}")
            for j, stop in enumerate(layer["legend"]):
                if not isinstance(stop, dict) or "color" not in stop or "label" not in stop:
                    errors.append(f"{prefix}: legend[{j}] missing 'color' or 'label'")
                elif not re.match(r"^#[0-9a-fA-F]{6}$", str(stop["color"])):
                    errors.append(f"{prefix}: legend[{j}].color '{stop['color']}' must be #rrggbb")

        # tileTemplate placeholders
        if "tileTemplate" in layer and isinstance(layer["tileTemplate"], str):
            tmpl = layer["tileTemplate"]
            for placeholder in ["{time}", "{z}", "{x}", "{y}"]:
                if placeholder not in tmpl:
                    errors.append(f"{prefix}: tileTemplate missing placeholder {placeholder}")

    print(f"  >> {len(layers)} layers, {len(errors)} errors")
    return errors


def validate_times_files():
    """Validate all *_times.json files."""
    print("[2/5] Validating *_times.json files...")
    errors = []

    # Discover layer IDs from layers.json
    layers, _ = load_json("data/metadata/layers.json")
    layer_ids = [la["id"] for la in layers] if isinstance(layers, list) else []
    if not layer_ids:
        return ["Cannot read layer IDs from layers.json"]

    for lid in layer_ids:
        path = f"data/series/{lid}_times.json"
        data, err = load_json(path)
        if err:
            errors.append(err)
            continue

        if not isinstance(data, list):
            errors.append(f"{path}: must be a JSON array")
            continue

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

        # Check sorted
        if all(isinstance(e, str) and re.match(r"^\d{4}-\d{2}$", e) for e in data):
            sorted_data = sorted(data)
            if data != sorted_data:
                errors.append(f"{path}: entries must be chronologically sorted")

    print(f"  >> {len(layer_ids)} files checked, {len(errors)} errors")
    return errors


def get_layer_ranges():
    """Get expected value ranges from layers.json for each layer."""
    layers, err = load_json("data/metadata/layers.json")
    if err or not isinstance(layers, list):
        return {}
    ranges = {}
    for layer in layers:
        lid = layer.get("id")
        rng = layer.get("range")
        if lid and isinstance(rng, dict) and "min" in rng and "max" in rng:
            ranges[lid] = (float(rng["min"]), float(rng["max"]))
    return ranges


def validate_series_files():
    """Validate all *_series.json files."""
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

        seen_times = set()
        for i, point in enumerate(data):
            prefix = f"{path}[{i}]"
            if not isinstance(point, dict):
                errors.append(f"{prefix}: must be an object")
                continue

            if "time" not in point:
                errors.append(f"{prefix}: missing 'time'")
            elif not isinstance(point["time"], str) or not re.match(r"^\d{4}-\d{2}$", point["time"]):
                errors.append(f"{prefix}: time '{point.get('time')}' must be YYYY-MM")
            elif point["time"] in seen_times:
                errors.append(f"{prefix}: duplicate time '{point['time']}'")
            else:
                seen_times.add(point["time"])

            if "value" not in point:
                errors.append(f"{prefix}: missing 'value'")
            elif not isinstance(point["value"], (int, float)):
                errors.append(f"{prefix}: value must be a number")
            else:
                import math
                val = point["value"]
                if math.isnan(val):
                    errors.append(f"{prefix}: value is NaN")
                elif math.isinf(val):
                    errors.append(f"{prefix}: value is Infinity")
                elif lid in ranges:
                    rmin, rmax = ranges[lid]
                    # Allow 10% margin outside declared range (for extreme values)
                    margin = (rmax - rmin) * 0.1
                    if val < rmin - margin or val > rmax + margin:
                        errors.append(
                            f"{prefix}: value {val} is far outside expected range "
                            f"[{rmin}, {rmax}] for {lid}"
                        )

    print(f"  >> {len(layer_ids)} files checked, {len(errors)} errors")
    return errors


def validate_stats_files():
    """Validate regions.json and area_stats.json."""
    print("[4/5] Validating stats files...")

    errors = []

    # Validate regions
    regions, err = load_json("data/stats/regions.json")
    if err:
        errors.append(err)
    elif not isinstance(regions, list):
        errors.append("regions.json must be a JSON array")
    else:
        region_ids = set()
        for i, region in enumerate(regions):
            prefix = f"Region [{i}]"

            for field in ["id", "name", "bounds"]:
                if field not in region:
                    errors.append(f"{prefix}: missing required field '{field}'")

            if "id" in region:
                rid = region["id"]
                if not isinstance(rid, str) or not re.match(r"^[a-z][a-z0-9_]*$", rid):
                    errors.append(f"{prefix}: id '{rid}' must match ^[a-z][a-z0-9_]*$")
                if rid in region_ids:
                    errors.append(f"{prefix}: duplicate id '{rid}'")
                if isinstance(rid, str):
                    region_ids.add(rid)

            if "bounds" in region and isinstance(region["bounds"], dict):
                b = region["bounds"]
                for bk in ["north", "south", "east", "west"]:
                    if bk not in b:
                        errors.append(f"{prefix}: bounds missing '{bk}'")
                    elif not isinstance(b[bk], (int, float)):
                        errors.append(f"{prefix}: bounds.{bk} must be a number")

                if all(k in b and isinstance(b[k], (int, float)) for k in ["north", "south", "east", "west"]):
                    if b["north"] <= b["south"]:
                        errors.append(f"{prefix}: bounds.north ({b['north']}) must be > bounds.south ({b['south']})")
                    if b["east"] <= b["west"]:
                        errors.append(f"{prefix}: bounds.east ({b['east']}) must be > bounds.west ({b['west']})")
                    if not (-90 <= b["north"] <= 90):
                        errors.append(f"{prefix}: bounds.north out of range [-90, 90]")
                    if not (-90 <= b["south"] <= 90):
                        errors.append(f"{prefix}: bounds.south out of range [-90, 90]")
                    if not (-180 <= b["east"] <= 180):
                        errors.append(f"{prefix}: bounds.east out of range [-180, 180]")
                    if not (-180 <= b["west"] <= 180):
                        errors.append(f"{prefix}: bounds.west out of range [-180, 180]")

        print(f"  >> regions.json: {len(regions)} regions, {len(errors)} errors so far")

    # Validate area_stats
    area_stats, err = load_json("data/stats/area_stats.json")
    if err:
        errors.append(err)
    elif not isinstance(area_stats, dict):
        errors.append("area_stats.json must be a JSON object")
    else:
        # Resolve valid region and layer IDs
        valid_regions = set()
        if isinstance(regions, list):
            for r in regions:
                if "id" in r:
                    valid_regions.add(r["id"])

        layers, _ = load_json("data/metadata/layers.json")
        valid_layers = set()
        layer_ranges = {}
        if isinstance(layers, list):
            for la in layers:
                lid = la.get("id")
                if lid:
                    valid_layers.add(lid)
                    rng = la.get("range", {})
                    if "min" in rng and "max" in rng:
                        layer_ranges[lid] = (float(rng["min"]), float(rng["max"]))

        stat_count = 0
        for region_id, layers_data in area_stats.items():
            if region_id not in valid_regions:
                errors.append(f"area_stats: region '{region_id}' not defined in regions.json")

            if not isinstance(layers_data, dict):
                errors.append(f"area_stats[{region_id}]: must be an object")
                continue

            for layer_id, times_data in layers_data.items():
                if layer_id not in valid_layers:
                    errors.append(f"area_stats[{region_id}]: layer '{layer_id}' not defined in layers.json")

                if not isinstance(times_data, dict):
                    errors.append(f"area_stats[{region_id}][{layer_id}]: must be an object")
                    continue

                for time_stamp, stats in times_data.items():
                    if not re.match(r"^\d{4}-\d{2}$", time_stamp):
                        errors.append(
                            f"area_stats[{region_id}][{layer_id}]: time '{time_stamp}' must be YYYY-MM"
                        )

                    if not isinstance(stats, dict):
                        errors.append(f"area_stats[{region_id}][{layer_id}][{time_stamp}]: must be an object")
                        continue

                    for sk in ["mean", "max", "min", "count"]:
                        if sk not in stats:
                            errors.append(
                                f"area_stats[{region_id}][{layer_id}][{time_stamp}]: missing '{sk}'"
                            )

                    if all(k in stats for k in ["mean", "max", "min", "count"]):
                        # Type checks
                        if not isinstance(stats["mean"], (int, float)):
                            errors.append(f"area_stats[{region_id}][{layer_id}][{time_stamp}]: mean must be number")
                        if not isinstance(stats["max"], (int, float)):
                            errors.append(f"area_stats[{region_id}][{layer_id}][{time_stamp}]: max must be number")
                        if not isinstance(stats["min"], (int, float)):
                            errors.append(f"area_stats[{region_id}][{layer_id}][{time_stamp}]: min must be number")
                        if not isinstance(stats["count"], int):
                            errors.append(f"area_stats[{region_id}][{layer_id}][{time_stamp}]: count must be integer")

                        # Logical checks (only if types are correct)
                        if all(
                            isinstance(stats[k], (int, float))
                            for k in ["mean", "max", "min"]
                        ):
                            if stats["min"] > stats["mean"]:
                                errors.append(
                                    f"area_stats[{region_id}][{layer_id}][{time_stamp}]: "
                                    f"min ({stats['min']}) > mean ({stats['mean']})"
                                )
                            if stats["mean"] > stats["max"]:
                                errors.append(
                                    f"area_stats[{region_id}][{layer_id}][{time_stamp}]: "
                                    f"mean ({stats['mean']}) > max ({stats['max']})"
                                )

                        if isinstance(stats["count"], int) and stats["count"] <= 0:
                            errors.append(
                                f"area_stats[{region_id}][{layer_id}][{time_stamp}]: "
                                f"count must be > 0, got {stats['count']}"
                            )

                        # Range check
                        if layer_id in layer_ranges:
                            rmin, rmax = layer_ranges[layer_id]
                            margin = (rmax - rmin) * 0.1
                            for vk in ["mean", "max", "min"]:
                                if isinstance(stats.get(vk), (int, float)):
                                    v = stats[vk]
                                    if v < rmin - margin or v > rmax + margin:
                                        errors.append(
                                            f"area_stats[{region_id}][{layer_id}][{time_stamp}]: "
                                            f"{vk} {v} is far outside layer range [{rmin}, {rmax}]"
                                        )

                    stat_count += 1

        print(f"  >> area_stats.json: {stat_count} stat entries, {len(errors)} total errors so far")

    return errors


def validate_times_series_consistency():
    """Check that times files and series files have matching time points."""
    print("[5/5] Validating time-series consistency...")
    errors = []

    layers, _ = load_json("data/metadata/layers.json")
    layer_ids = [la["id"] for la in layers] if isinstance(layers, list) else []
    if not layer_ids:
        return ["Cannot read layer IDs from layers.json"]

    for lid in layer_ids:
        times_data, times_err = load_json(f"data/series/{lid}_times.json")
        series_data, series_err = load_json(f"data/series/{lid}_series.json")

        if times_err or series_err:
            continue

        if isinstance(times_data, list) and isinstance(series_data, list):
            times_set = set(times_data)
            series_times = set()
            for pt in series_data:
                if isinstance(pt, dict) and "time" in pt:
                    series_times.add(pt["time"])

            missing_in_series = times_set - series_times
            extra_in_series = series_times - times_set

            if missing_in_series:
                errors.append(f"{lid}: times in *_times.json but not in *_series.json: {sorted(missing_in_series)}")
            if extra_in_series:
                errors.append(f"{lid}: times in *_series.json but not in *_times.json: {sorted(extra_in_series)}")

    print(f"  >> {len(errors)} consistency errors")
    return errors


def main():
    """Run all validations and report results."""
    print("=" * 60)
    print("  Remote Sensing Data — Validation Script")
    print("=" * 60)
    print(f"  Project root: {PROJECT_ROOT}")
    print()

    all_errors = []
    all_errors.extend(validate_layers())
    all_errors.extend(validate_times_files())
    all_errors.extend(validate_series_files())
    all_errors.extend(validate_stats_files())
    all_errors.extend(validate_times_series_consistency())

    print()
    print("=" * 60)
    if all_errors:
        print(f"  VALIDATION FAILED — {len(all_errors)} error(s):")
        for e in all_errors:
            print(f"    - {e}")
        print("=" * 60)
        sys.exit(1)
    else:
        print("  VALIDATION PASSED — All checks passed!")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
