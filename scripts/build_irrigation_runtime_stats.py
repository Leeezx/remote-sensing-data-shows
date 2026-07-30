"""Build compact runtime shards from offline irrigation statistics."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from backend.ssm_legend import build_dynamic_legend


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
