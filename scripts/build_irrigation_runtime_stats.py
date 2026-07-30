"""Build compact runtime shards from offline irrigation statistics."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.ssm_legend import build_dynamic_legend


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _county_code_from_parent_id(parent_id: object) -> str:
    value = str(parent_id)
    if value.startswith("156"):
        value = value[3:]
    if len(value) != 6 or not value.isdigit():
        raise ValueError(f"invalid township parentId: {parent_id}")
    return value


def _load_township_ids_by_county(
    township_root: Path,
) -> dict[str, set[str]]:
    manifest = _read_json(township_root / "manifest.json")
    chunks = manifest.get("chunks") if isinstance(manifest, dict) else None
    if not isinstance(chunks, dict):
        raise ValueError("township chunk manifest must contain a chunks object")
    if manifest.get("chunkCount") != len(chunks):
        raise ValueError("township chunk manifest chunkCount does not match chunks")

    township_ids_by_county: dict[str, set[str]] = {}
    for county_code, chunk_info in sorted(chunks.items()):
        if len(county_code) != 6 or not county_code.isdigit():
            raise ValueError(f"invalid county code in chunk manifest: {county_code}")
        if not isinstance(chunk_info, dict):
            raise ValueError(f"invalid chunk metadata for county {county_code}")
        if (
            _county_code_from_parent_id(chunk_info.get("countyId"))
            != county_code
        ):
            raise ValueError(
                f"chunk countyId does not match county code {county_code}"
            )
        chunk_path = township_root / f"{county_code}.geojson"
        chunk = _read_json(chunk_path)
        features = chunk.get("features") if isinstance(chunk, dict) else None
        if not isinstance(features, list):
            raise ValueError(
                f"township chunk {county_code} must contain a features array"
            )
        if chunk_info.get("featureCount") != len(features):
            raise ValueError(
                f"township chunk {county_code} featureCount does not match"
            )
        region_ids: set[str] = set()
        for feature in features:
            properties = (
                feature.get("properties") if isinstance(feature, dict) else None
            )
            if not isinstance(properties, dict):
                raise ValueError(
                    f"township chunk {county_code} has invalid feature properties"
                )
            region_id = str(properties.get("id", ""))
            if not region_id:
                raise ValueError(
                    f"township chunk {county_code} has a feature without an id"
                )
            parent_code = _county_code_from_parent_id(
                properties.get("parentId")
            )
            if parent_code != county_code:
                raise ValueError(
                    f"township {region_id} parentId does not match "
                    f"county {county_code}"
                )
            region_ids.add(region_id)
        township_ids_by_county[county_code] = region_ids
    return township_ids_by_county


def _source_shard(region_id: str) -> str:
    if len(region_id) == 12 and region_id.isdigit():
        return region_id[:6]
    return "misc"


def _mean_annual(region_id: str, entry: dict[str, Any]) -> float | None:
    annual = entry.get("annual")
    if not isinstance(annual, list) or not annual:
        return None
    values = [float(point["value"]) for point in annual]
    if not all(math.isfinite(value) for value in values):
        raise ValueError(f"annual values for {region_id} must be finite")
    return round(sum(values) / len(values), 1)


def _averages_payload(
    level: str,
    region_ids: list[str],
    names: dict[str, str],
    level_series: dict[str, dict[str, Any]],
    base_legend: list[dict[str, Any]],
    unit: str,
) -> dict[str, Any]:
    averages = [
        {
            "regionId": region_id,
            "name": names[region_id],
            "average": _mean_annual(region_id, level_series[region_id]),
        }
        for region_id in sorted(region_ids)
    ]
    valid = np.asarray(
        [item["average"] for item in averages if item["average"] is not None],
        dtype=float,
    )
    legend = (
        build_dynamic_legend(valid, base_legend, unit)
        if valid.size and base_legend
        else [dict(item) for item in base_legend]
    )
    return {
        "level": level,
        "unit": unit,
        "averages": averages,
        "legend": legend,
    }


def build_runtime_payloads(
    series_data: dict[str, Any],
    regions: list[dict[str, Any]],
    base_legend: list[dict[str, Any]],
    township_ids_by_county: dict[str, set[str]],
    source_sha256: str,
) -> dict[str, dict[str, Any]]:
    """Return every JSON runtime artifact keyed by its relative path."""
    unit = str(series_data.get("unit", "万m³"))
    county_series = dict(series_data.get("county", {}))
    township_series = dict(series_data.get("township", {}))
    names = {
        str(region["id"]): str(region["name"])
        for region in regions
        if region.get("id") is not None and region.get("name") is not None
    }
    for level_name, level_data in (
        ("county", county_series),
        ("township", township_series),
    ):
        missing_names = sorted(set(level_data) - set(names))
        if missing_names:
            raise ValueError(
                f"{level_name} series IDs missing from region catalog: "
                + ", ".join(missing_names[:10])
            )

    visible_ids = (
        set().union(*township_ids_by_county.values())
        if township_ids_by_county
        else set()
    )
    missing_series = sorted(visible_ids - set(township_series))
    if missing_series:
        raise ValueError(
            "vector township IDs missing from township series: "
            + ", ".join(missing_series[:10])
        )

    payloads: dict[str, dict[str, Any]] = {}
    payloads["averages/county.json"] = _averages_payload(
        "county",
        list(county_series),
        names,
        county_series,
        base_legend,
        unit,
    )
    for county_code, township_ids in sorted(township_ids_by_county.items()):
        payloads[f"averages/township_by_county/{county_code}.json"] = (
            _averages_payload(
                "township",
                list(township_ids),
                names,
                township_series,
                base_legend,
                unit,
            )
        )

    payloads["series/county.json"] = {
        "unit": unit,
        "regions": {
            region_id: county_series[region_id]
            for region_id in sorted(county_series)
        },
    }
    township_index = {
        region_id: _source_shard(region_id)
        for region_id in sorted(township_series)
    }
    payloads["series/township_index.json"] = township_index
    for shard in sorted(set(township_index.values())):
        payloads[f"series/township_by_source_code/{shard}.json"] = {
            region_id: township_series[region_id]
            for region_id, indexed_shard in township_index.items()
            if indexed_shard == shard
        }

    ownership_count = Counter(
        region_id
        for township_ids in township_ids_by_county.values()
        for region_id in township_ids
    )
    mapped_ids = set(ownership_count)
    payloads["manifest.json"] = {
        "schemaVersion": 1,
        "unit": unit,
        "sourceSha256": source_sha256,
        "countyCount": len(county_series),
        "sourceTownshipCount": len(township_series),
        "mappedTownshipCount": len(mapped_ids),
        "mappedTownshipPairCount": sum(ownership_count.values()),
        "crossCountyTownshipCount": sum(
            count > 1 for count in ownership_count.values()
        ),
        "unmappedTownshipCount": len(set(township_series) - mapped_ids),
        "averageShardCount": len(township_ids_by_county),
        "seriesShardCount": len(set(township_index.values())),
        "artifacts": sorted(
            path for path in payloads if path != "manifest.json"
        ),
    }
    return payloads


def validate_runtime_tree(
    runtime_root: Path,
    series_data: dict[str, Any],
    township_ids_by_county: dict[str, set[str]],
) -> dict[str, Any]:
    """Reload and cross-check a complete staged runtime tree."""
    manifest = _read_json(runtime_root / "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != 1:
        raise ValueError("runtime manifest has an unsupported schema")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not all(
        isinstance(path, str) for path in artifacts
    ):
        raise ValueError("runtime manifest artifacts must be a string array")
    for relative_path in artifacts:
        artifact = _read_json(runtime_root / relative_path)
        if not isinstance(artifact, dict):
            raise ValueError(
                f"runtime artifact must contain an object: {relative_path}"
            )

    county_series = dict(series_data.get("county", {}))
    township_series = dict(series_data.get("township", {}))
    county_payload = _read_json(runtime_root / "series/county.json")
    if county_payload.get("regions") != county_series:
        raise ValueError("runtime county series do not match the source")

    index = _read_json(runtime_root / "series/township_index.json")
    if set(index) != set(township_series):
        raise ValueError("runtime township index does not match the source")
    stored_townships: dict[str, Any] = {}
    for shard in sorted(set(index.values())):
        shard_payload = _read_json(
            runtime_root
            / "series/township_by_source_code"
            / f"{shard}.json"
        )
        overlap = set(stored_townships) & set(shard_payload)
        if overlap:
            raise ValueError(
                "township series are duplicated across shards: "
                + ", ".join(sorted(overlap)[:10])
            )
        stored_townships.update(shard_payload)
    if stored_townships != township_series:
        raise ValueError("runtime township series do not match the source")
    if any(
        region_id not in stored_townships
        or index.get(region_id) != _source_shard(region_id)
        for region_id in township_series
    ):
        raise ValueError("runtime township index points to the wrong shard")

    average_pairs: set[tuple[str, str]] = set()
    for county_code, expected_ids in township_ids_by_county.items():
        payload = _read_json(
            runtime_root
            / "averages/township_by_county"
            / f"{county_code}.json"
        )
        actual_ids = {
            str(item.get("regionId"))
            for item in payload.get("averages", [])
            if isinstance(item, dict)
        }
        if actual_ids != expected_ids:
            raise ValueError(
                f"runtime township averages do not match county {county_code}"
            )
        average_pairs.update(
            (county_code, region_id) for region_id in actual_ids
        )

    mapped_ids = {region_id for _, region_id in average_pairs}
    owner_counts = Counter(region_id for _, region_id in average_pairs)
    expected_counts = {
        "countyCount": len(county_series),
        "sourceTownshipCount": len(township_series),
        "mappedTownshipCount": len(mapped_ids),
        "mappedTownshipPairCount": len(average_pairs),
        "crossCountyTownshipCount": sum(
            count > 1 for count in owner_counts.values()
        ),
        "unmappedTownshipCount": len(set(township_series) - mapped_ids),
        "averageShardCount": len(township_ids_by_county),
        "seriesShardCount": len(set(index.values())),
    }
    for field, expected in expected_counts.items():
        if manifest.get(field) != expected:
            raise ValueError(
                f"runtime manifest {field} does not match generated artifacts"
            )
    return manifest


def _publish_staged_directory(staged: Path, output: Path) -> None:
    """Atomically swap a complete runtime tree and restore failures."""
    backup = output.with_name(f".{output.name}.backup")
    if backup.exists():
        shutil.rmtree(backup)
    if output.exists():
        output.replace(backup)
    try:
        staged.replace(output)
    except BaseException:
        if output.exists():
            shutil.rmtree(output)
        if backup.exists():
            backup.replace(output)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def build_runtime_stats(
    source_path: Path,
    regions_path: Path,
    layer_path: Path,
    township_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Build, validate, and atomically publish runtime statistics."""
    source_bytes = source_path.read_bytes()
    series_data = json.loads(source_bytes)
    regions = _read_json(regions_path)
    layer = _read_json(layer_path)
    if not isinstance(series_data, dict):
        raise ValueError("irrigation series source must contain an object")
    if not isinstance(regions, list):
        raise ValueError("irrigation regions source must contain an array")
    if not isinstance(layer, dict):
        raise ValueError("irrigation layer source must contain an object")
    township_ids_by_county = _load_township_ids_by_county(township_root)
    payloads = build_runtime_payloads(
        series_data,
        regions,
        list(layer.get("legend", [])),
        township_ids_by_county,
        hashlib.sha256(source_bytes).hexdigest(),
    )

    output_root.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(
        tempfile.mkdtemp(
            prefix=f".{output_root.name}-",
            dir=output_root.parent,
        )
    )
    try:
        for relative_path, payload in payloads.items():
            _write_json(staged / relative_path, payload)
        validate_runtime_tree(staged, series_data, township_ids_by_county)
        _publish_staged_directory(staged, output_root)
    except BaseException:
        if staged.exists():
            shutil.rmtree(staged)
        raise
    return payloads["manifest.json"]


def _tree_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def check_runtime_stats(
    source_path: Path,
    regions_path: Path,
    layer_path: Path,
    township_root: Path,
    output_root: Path,
) -> bool:
    """Return whether a fresh validated build matches published artifacts."""
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output_root.name}-check-",
        dir=output_root.parent,
    ) as temp_dir:
        candidate = Path(temp_dir) / output_root.name
        build_runtime_stats(
            source_path,
            regions_path,
            layer_path,
            township_root,
            candidate,
        )
        return _tree_hashes(candidate) == _tree_hashes(output_root)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build compact irrigation runtime statistics"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            PROJECT_ROOT / "data/stats/irrigation_region_series.json"
        ),
    )
    parser.add_argument(
        "--regions",
        type=Path,
        default=PROJECT_ROOT / "data/stats/irrigation_regions.json",
    )
    parser.add_argument(
        "--layer",
        type=Path,
        default=PROJECT_ROOT / "data/metadata/irrigation_layer.json",
    )
    parser.add_argument(
        "--township-root",
        type=Path,
        default=(
            PROJECT_ROOT
            / "data/vectors/irrigation/township_by_county"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data/stats/irrigation_runtime",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        matches = check_runtime_stats(
            args.source,
            args.regions,
            args.layer,
            args.township_root,
            args.output,
        )
        print(
            "Irrigation runtime statistics are current."
            if matches
            else "Irrigation runtime statistics differ from a fresh build."
        )
        return 0 if matches else 1

    manifest = build_runtime_stats(
        args.source,
        args.regions,
        args.layer,
        args.township_root,
        args.output,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
