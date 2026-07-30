# Irrigation Region Statistics Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace request-time parsing of the 229.94 MiB irrigation statistics file with validated runtime shards, add application and proxy caching, and let the county map appear independently of statistical coloring.

**Architecture:** Keep `data/stats/irrigation_region_series.json` as an offline source only. A transactional builder publishes compact runtime artifacts under `data/stats/irrigation_runtime/`: county averages and series are single files, township averages are grouped by the current county vector chunks, and township series are grouped by source-code prefix with an index for exact lookup. FastAPI loads only the requested artifact through bounded, file-version-aware LRU caches and returns cache validators; Nginx caches the two read-only statistics endpoints. The React page starts vector and averages requests concurrently, but renders the vector as soon as it arrives.

**Tech Stack:** Python 3.12, FastAPI, pytest, NumPy, React 19, TypeScript, Vitest, Testing Library, Nginx, Docker Compose.

## Global Constraints

- Preserve the existing JSON contracts for `GET /api/irrigation/regions/averages` and `GET /api/irrigation/series`.
- Preserve `422` for township averages without `countyId`, `404` for unknown regions, and existing annual/monthly summaries.
- A township ID may belong to more than one current county vector chunk. Include it in every matching averages shard but store its time series exactly once.
- Keep the 57 source-series IDs that are absent from current vectors queryable through the series endpoint; do not place them in averages shards.
- Derive manifest counts and shard lists from generated data. Do not hard-code production counts.
- Publish into a staging directory, validate the full tree, then atomically replace the destination with rollback on failure.
- Runtime routes and readiness probes must never call `get_irrigation_region_series()`.
- Cache keys must include file path, modification time, and size so a published artifact refresh invalidates process-local values.
- Limit averages and township-series shard caches to 64 entries each.
- Performance gates on the real dataset: cold county averages at most 300 ms, hot request at most 100 ms, and per-worker resident-memory increase below 100 MiB.
- Follow repository style: four spaces in Python; two spaces, single quotes, and no semicolons in TypeScript.

---

## Task 1: Build deterministic runtime payloads in memory

**Files:**

- Create: `scripts/build_irrigation_runtime_stats.py`
- Create: `backend/tests/test_build_irrigation_runtime_stats.py`
- Reference: `backend/irrigation_stats.py`
- Reference: `backend/ssm_legend.py`

- [ ] **Step 1: Write failing tests for the double-index model**

Add focused fixtures that prove vector ownership, not source-prefix ownership, controls township averages:

```python
from scripts.build_irrigation_runtime_stats import build_runtime_payloads


BASE_LEGEND = [
    {"value": 0, "color": "#f7fbff", "label": "低"},
    {"value": 10, "color": "#08306b", "label": "高"},
]


def entry(name: str, *values: float) -> dict:
    return {
        "name": name,
        "annual": [
            {"time": str(2020 + index), "value": value}
            for index, value in enumerate(values)
        ],
        "monthly": [],
    }


def test_runtime_payloads_follow_current_vector_ownership():
    series = {
        "unit": "万m³",
        "county": {"130502": entry("桥东区", 10, 20)},
        "township": {
            "130521001000": entry("旧编码街道", 3, 5),
            "custom-history-id": entry("历史区域", 7),
        },
    }
    regions = [
        {"id": "130502", "name": "桥东区", "level": "county", "parentId": None},
        {
            "id": "130521001000",
            "name": "旧编码街道",
            "level": "township",
            "parentId": None,
        },
        {
            "id": "custom-history-id",
            "name": "历史区域",
            "level": "township",
            "parentId": None,
        },
    ]
    result = build_runtime_payloads(
        series,
        regions,
        BASE_LEGEND,
        {
            "130502": {"130521001000"},
            "130503": {"130521001000"},
        },
        "source-digest",
    )

    assert result["averages/county.json"]["averages"] == [
        {"regionId": "130502", "name": "桥东区", "average": 15.0}
    ]
    assert result["averages/township_by_county/130502.json"]["averages"] == [
        {"regionId": "130521001000", "name": "旧编码街道", "average": 4.0}
    ]
    assert result["averages/township_by_county/130503.json"]["averages"] == [
        {"regionId": "130521001000", "name": "旧编码街道", "average": 4.0}
    ]
    assert result["series/township_index.json"] == {
        "130521001000": "130521",
        "custom-history-id": "misc",
    }
    assert set(result["series/township_by_source_code/130521.json"]) == {
        "130521001000"
    }
    assert set(result["series/township_by_source_code/misc.json"]) == {
        "custom-history-id"
    }
    assert result["manifest.json"]["mappedTownshipPairCount"] == 2
    assert result["manifest.json"]["crossCountyTownshipCount"] == 1
    assert result["manifest.json"]["unmappedTownshipCount"] == 1
```

Add failure tests for a vector ID missing from the source series and for non-finite annual values:

```python
import math

import pytest


def test_runtime_payloads_reject_unknown_vector_id():
    with pytest.raises(ValueError, match="missing from township series"):
        build_runtime_payloads(
            {"unit": "万m³", "county": {}, "township": {}},
            [],
            BASE_LEGEND,
            {"130502": {"130502001000"}},
            "digest",
        )


def test_runtime_payloads_reject_non_finite_value():
    with pytest.raises(ValueError, match="finite"):
        build_runtime_payloads(
            {
                "unit": "万m³",
                "county": {"130502": entry("桥东区", math.inf)},
                "township": {},
            },
            [{"id": "130502", "name": "桥东区", "level": "county"}],
            BASE_LEGEND,
            {},
            "digest",
        )
```

- [ ] **Step 2: Run the tests and confirm the module is missing**

Run:

```powershell
python -m pytest backend/tests/test_build_irrigation_runtime_stats.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'scripts.build_irrigation_runtime_stats'`.

- [ ] **Step 3: Implement the pure payload builder**

Create the module with typed helpers and deterministic ordering:

```python
from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from backend.ssm_legend import build_dynamic_legend


def _source_shard(region_id: str) -> str:
    return region_id[:6] if len(region_id) == 12 and region_id.isdigit() else "misc"


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
    return {"level": level, "unit": unit, "averages": averages, "legend": legend}


def build_runtime_payloads(
    series_data: dict[str, Any],
    regions: list[dict[str, Any]],
    base_legend: list[dict[str, Any]],
    township_ids_by_county: dict[str, set[str]],
    source_sha256: str,
) -> dict[str, dict[str, Any]]:
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

    visible_ids = set().union(*township_ids_by_county.values()) if township_ids_by_county else set()
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
```

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
python -m pytest backend/tests/test_build_irrigation_runtime_stats.py -v
```

Expected: all payload-builder tests pass.

- [ ] **Step 5: Commit the pure builder**

```powershell
git add scripts/build_irrigation_runtime_stats.py backend/tests/test_build_irrigation_runtime_stats.py
git commit -m "feat: build irrigation runtime statistics payloads"
```

---

## Task 2: Add transactional filesystem publishing and precompute integration

**Files:**

- Modify: `scripts/build_irrigation_runtime_stats.py`
- Modify: `backend/precompute_irrigation.py`
- Modify: `backend/tests/test_build_irrigation_runtime_stats.py`
- Modify: `backend/tests/test_precompute_irrigation.py`

- [ ] **Step 1: Write failing filesystem and CLI tests**

Add tests that create two county vector chunks and assert a complete tree is published:

```python
import json
from pathlib import Path

from scripts.build_irrigation_runtime_stats import build_runtime_stats


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_build_runtime_stats_publishes_valid_tree(tmp_path):
    source = tmp_path / "irrigation_region_series.json"
    regions = tmp_path / "irrigation_regions.json"
    layer = tmp_path / "irrigation_layer.json"
    chunks = tmp_path / "township_by_county"
    output = tmp_path / "runtime"
    write_json(
        source,
        {
            "unit": "万m³",
            "county": {"130502": entry("桥东区", 10)},
            "township": {"130521001000": entry("旧编码街道", 4)},
        },
    )
    write_json(
        regions,
        [
            {"id": "130502", "name": "桥东区", "level": "county"},
            {
                "id": "130521001000",
                "name": "旧编码街道",
                "level": "township",
            },
        ],
    )
    write_json(layer, {"legend": BASE_LEGEND})
    write_json(
        chunks / "manifest.json",
        {"chunks": [{"countyCode": "130502", "file": "130502.geojson"}]},
    )
    write_json(
        chunks / "130502.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": {
                        "id": "130521001000",
                        "parentId": "156130502",
                    },
                }
            ],
        },
    )

    manifest = build_runtime_stats(source, regions, layer, chunks, output)

    assert manifest["sourceTownshipCount"] == 1
    assert (output / "manifest.json").is_file()
    assert (
        json.loads(
            (output / "averages/township_by_county/130502.json").read_text(
                encoding="utf-8"
            )
        )["averages"][0]["regionId"]
        == "130521001000"
    )
```

Add a rollback test: publish a valid destination, corrupt the next source, assert the old destination remains byte-for-byte unchanged. Add a precompute test that calls a new `publish_runtime_stats()` helper only for a complete, non-limited run and never for `--limit`, `--regions-only`, or a run with errors.

- [ ] **Step 2: Run the tests and confirm missing interfaces**

Run:

```powershell
python -m pytest backend/tests/test_build_irrigation_runtime_stats.py backend/tests/test_precompute_irrigation.py -v
```

Expected: failures name `build_runtime_stats` and `publish_runtime_stats`.

- [ ] **Step 3: Implement vector scanning, validation, and atomic publish**

Add these public interfaces:

```python
def build_runtime_stats(
    source_path: Path,
    regions_path: Path,
    layer_path: Path,
    township_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    source_bytes = source_path.read_bytes()
    series_data = json.loads(source_bytes)
    regions = json.loads(regions_path.read_text(encoding="utf-8"))
    layer = json.loads(layer_path.read_text(encoding="utf-8"))
    township_ids_by_county = _load_township_ids_by_county(township_root)
    payloads = build_runtime_payloads(
        series_data,
        regions,
        list(layer.get("legend", [])),
        township_ids_by_county,
        hashlib.sha256(source_bytes).hexdigest(),
    )
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
```

Implement `_load_township_ids_by_county()` by reading the chunk manifest entries, then each declared GeoJSON file, taking the first six digits from `properties.parentId` after removing the `156` prefix when present, and verifying that the resolved code matches the manifest/chunk filename. Reject duplicate manifest entries, missing files, malformed features, and missing IDs.

Implement `validate_runtime_tree()` to reload every path listed in the manifest and assert:

- county series keys equal the source county keys;
- township index keys equal the source township keys;
- every indexed township appears in exactly one series shard with unchanged data;
- every vector county/ID pair appears in its averages shard;
- no non-vector township appears in an averages shard;
- manifest counts equal the recomputed counts.

Use the proven backup-and-restore replacement pattern:

```python
def _publish_staged_directory(staged: Path, output: Path) -> None:
    backup = output.with_name(f".{output.name}.backup")
    if backup.exists():
        shutil.rmtree(backup)
    if output.exists():
        output.replace(backup)
    try:
        staged.replace(output)
    except BaseException:
        if backup.exists() and not output.exists():
            backup.replace(output)
        raise
    if backup.exists():
        shutil.rmtree(backup)
```

Add CLI arguments with repository defaults:

```python
parser.add_argument(
    "--source",
    type=Path,
    default=PROJECT_ROOT / "data/stats/irrigation_region_series.json",
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
    default=PROJECT_ROOT / "data/vectors/irrigation/township_by_county",
)
parser.add_argument(
    "--output",
    type=Path,
    default=PROJECT_ROOT / "data/stats/irrigation_runtime",
)
parser.add_argument("--check", action="store_true")
```

`--check` must build and validate in a temporary sibling directory, compare file hashes with the current output, report drift, and exit non-zero without replacing the output.

- [ ] **Step 4: Integrate safe publication into precompute**

Expose a helper in `backend/precompute_irrigation.py`:

```python
def publish_runtime_stats() -> dict:
    from scripts.build_irrigation_runtime_stats import build_runtime_stats

    return build_runtime_stats(
        OUTPUT_PATH,
        REGIONS_PATH,
        PROJECT_ROOT / "data/metadata/irrigation_layer.json",
        PROJECT_ROOT / "data/vectors/irrigation/township_by_county",
        PROJECT_ROOT / "data/stats/irrigation_runtime",
    )
```

Call it only after a full run has zero errors and no `--limit`. Keep `--regions-only` unchanged. Print the manifest counts so operators can compare source, mapped, cross-county, and unmapped totals.

- [ ] **Step 5: Run builder and precompute tests**

Run:

```powershell
python -m pytest backend/tests/test_build_irrigation_runtime_stats.py backend/tests/test_precompute_irrigation.py -v
```

Expected: all tests pass, including rollback and partial-run protection.

- [ ] **Step 6: Commit transactional publication**

```powershell
git add scripts/build_irrigation_runtime_stats.py backend/precompute_irrigation.py backend/tests/test_build_irrigation_runtime_stats.py backend/tests/test_precompute_irrigation.py
git commit -m "feat: publish irrigation runtime shards transactionally"
```

---

## Task 3: Add bounded runtime loaders and lightweight readiness checks

**Files:**

- Create: `backend/irrigation_runtime_stats.py`
- Create: `backend/tests/test_irrigation_runtime_stats.py`
- Modify: `backend/runtime_config.py`
- Modify: `backend/readiness.py`
- Modify: `backend/tests/test_readiness.py`

- [ ] **Step 1: Write failing loader tests**

Create a minimal runtime tree fixture and test:

```python
from backend import irrigation_runtime_stats


def test_county_averages_load_only_core_file(runtime_root, monkeypatch):
    monkeypatch.setattr(
        irrigation_runtime_stats,
        "IRRIGATION_RUNTIME_STATS_ROOT",
        runtime_root,
    )
    irrigation_runtime_stats.clear_runtime_stats_caches()

    payload = irrigation_runtime_stats.load_region_averages("county")

    assert payload["level"] == "county"


def test_township_series_uses_index_and_returns_defensive_copy(
    runtime_root,
    monkeypatch,
):
    monkeypatch.setattr(
        irrigation_runtime_stats,
        "IRRIGATION_RUNTIME_STATS_ROOT",
        runtime_root,
    )
    irrigation_runtime_stats.clear_runtime_stats_caches()

    first = irrigation_runtime_stats.load_region_series_entry(
        "township",
        "130521001000",
    )
    assert first is not None
    unit, entry = first
    assert unit == "万m³"
    entry["annual"][0]["value"] = -1

    second = irrigation_runtime_stats.load_region_series_entry(
        "township",
        "130521001000",
    )
    assert second is not None
    assert second[1]["annual"][0]["value"] == 4
```

Add tests for:

- county series lookup;
- unknown township returns `None`;
- missing/corrupt manifest or shard raises `IrrigationRuntimeDataError`;
- changed file mtime/size returns fresh content;
- after loading 65 distinct shards, `_load_series_shard.cache_info().currsize == 64`.

- [ ] **Step 2: Run the tests and confirm missing loader**

Run:

```powershell
python -m pytest backend/tests/test_irrigation_runtime_stats.py -v
```

Expected: collection fails because `backend.irrigation_runtime_stats` does not exist.

- [ ] **Step 3: Implement file-version-aware caches**

Add the runtime root:

```python
IRRIGATION_RUNTIME_STATS_ROOT = path_env(
    "IRRIGATION_RUNTIME_STATS_ROOT",
    PROJECT_ROOT / "data" / "stats" / "irrigation_runtime",
)
```

Implement the loader:

```python
class IrrigationRuntimeDataError(RuntimeError):
    pass


def _version(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise IrrigationRuntimeDataError(
            f"irrigation runtime artifact unavailable: {path.name}"
        ) from exc
    return str(path), stat.st_mtime_ns, stat.st_size


def _read_object(path: str) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IrrigationRuntimeDataError(
            f"invalid irrigation runtime artifact: {Path(path).name}"
        ) from exc
    if not isinstance(payload, dict):
        raise IrrigationRuntimeDataError(
            f"irrigation runtime artifact must be an object: {Path(path).name}"
        )
    return payload


@lru_cache(maxsize=8)
def _load_core(path: str, mtime_ns: int, size: int) -> dict:
    del mtime_ns, size
    return _read_object(path)


@lru_cache(maxsize=64)
def _load_average_shard(path: str, mtime_ns: int, size: int) -> dict:
    del mtime_ns, size
    return _read_object(path)


@lru_cache(maxsize=64)
def _load_series_shard(path: str, mtime_ns: int, size: int) -> dict:
    del mtime_ns, size
    return _read_object(path)


def load_region_averages(
    level: str,
    county_id: str | None = None,
) -> dict:
    if level == "county":
        path = IRRIGATION_RUNTIME_STATS_ROOT / "averages/county.json"
        return copy.deepcopy(_load_core(*_version(path)))
    if level != "township":
        raise ValueError(f"unsupported irrigation region level: {level}")
    if county_id is None:
        raise ValueError("countyId is required for township averages")
    county_code = county_code_from_id(county_id)
    path = (
        IRRIGATION_RUNTIME_STATS_ROOT
        / "averages/township_by_county"
        / f"{county_code}.json"
    )
    return copy.deepcopy(_load_average_shard(*_version(path)))


def load_region_series_entry(
    level: str,
    region_id: str,
) -> tuple[str, dict] | None:
    if level == "county":
        path = IRRIGATION_RUNTIME_STATS_ROOT / "series/county.json"
        payload = _load_core(*_version(path))
        entry = payload.get("regions", {}).get(region_id)
        return (
            (str(payload.get("unit", "万m³")), copy.deepcopy(entry))
            if isinstance(entry, dict)
            else None
        )
    if level != "township":
        raise ValueError(f"unsupported irrigation region level: {level}")
    index_path = IRRIGATION_RUNTIME_STATS_ROOT / "series/township_index.json"
    index = _load_core(*_version(index_path))
    shard = index.get(region_id)
    if not isinstance(shard, str):
        return None
    shard_path = (
        IRRIGATION_RUNTIME_STATS_ROOT
        / "series/township_by_source_code"
        / f"{shard}.json"
    )
    entry = _load_series_shard(*_version(shard_path)).get(region_id)
    return (
        ("万m³", copy.deepcopy(entry))
        if isinstance(entry, dict)
        else None
    )


def clear_runtime_stats_caches() -> None:
    _load_core.cache_clear()
    _load_average_shard.cache_clear()
    _load_series_shard.cache_clear()
```

Read the unit from `manifest.json` for township results, cache that manifest through `_load_core`, and validate `schemaVersion == 1`.

- [ ] **Step 4: Replace readiness's monolithic probe**

Change `collect_readiness_failures()` to call a new read-only validator:

```python
def probe_irrigation_runtime(root: Path) -> bool:
    required = (
        root / "manifest.json",
        root / "averages/county.json",
        root / "series/county.json",
        root / "series/township_index.json",
    )
    return all(probe_json_object(path) for path in required)
```

Use the stable failure identifier `irrigation_runtime_stats`. The readiness test fixture must create all four valid JSON objects and must prove malformed core JSON fails without mentioning a host path.

- [ ] **Step 5: Run loader and readiness tests**

Run:

```powershell
python -m pytest backend/tests/test_irrigation_runtime_stats.py backend/tests/test_readiness.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit the runtime loader**

```powershell
git add backend/irrigation_runtime_stats.py backend/runtime_config.py backend/readiness.py backend/tests/test_irrigation_runtime_stats.py backend/tests/test_readiness.py
git commit -m "feat: load irrigation statistics from bounded shards"
```

---

## Task 4: Migrate the API and add HTTP validators

**Files:**

- Modify: `backend/routers/irrigation.py`
- Modify: `backend/tests/test_irrigation.py`
- Reference: `frontend/src/services/api.ts`
- Reference: `frontend/src/types/index.ts`

- [ ] **Step 1: Replace legacy fixtures with runtime-loader fixtures**

Monkeypatch the two new loader functions in API contract tests. Add a guard that fails if either endpoint touches the legacy loader:

```python
def fail_legacy_loader():
    raise AssertionError("runtime API must not load the monolithic series file")


def test_irrigation_statistics_routes_do_not_use_legacy_loader(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        "backend.routers.irrigation.get_irrigation_region_series",
        fail_legacy_loader,
        raising=False,
    )
    monkeypatch.setattr(
        "backend.routers.irrigation.load_region_averages",
        lambda level, county_id=None: {
            "level": level,
            "unit": "万m³",
            "averages": [],
            "legend": [],
        },
    )
    monkeypatch.setattr(
        "backend.routers.irrigation.load_region_series_entry",
        lambda level, region_id: (
            "万m³",
            {
                "name": "桥东区",
                "annual": [{"time": "2024", "value": 10}],
                "monthly": [],
            },
        ),
    )

    assert client.get(
        "/api/irrigation/regions/averages",
        params={"level": "county"},
    ).status_code == 200
    assert client.get(
        "/api/irrigation/series",
        params={
            "level": "county",
            "regionId": "130502",
            "period": "annual",
        },
    ).status_code == 200
```

Add tests asserting:

- `Cache-Control: public, max-age=3600`;
- a strong quoted `ETag` is returned;
- the same request with `If-None-Match` returns `304` and an empty body;
- a loader failure maps to `503`;
- existing `404` and `422` contracts remain unchanged.

- [ ] **Step 2: Run the API tests and confirm failures**

Run:

```powershell
python -m pytest backend/tests/test_irrigation.py -v
```

Expected: new tests fail because routes still call the monolithic loader and do not return validators.

- [ ] **Step 3: Add one serialization helper**

Import `Request`, `Response`, and `JSONResponse`, then add:

```python
def _cached_json_response(request: Request, payload: dict) -> Response:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {
        "Cache-Control": "public, max-age=3600",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(
        content=body,
        media_type="application/json",
        headers=headers,
    )
```

Change both route signatures to accept `request: Request`. `irrigation_region_averages()` must call `load_region_averages(level, countyId)`. `irrigation_series()` must call `load_region_series_entry(level, regionId)`, keep the existing period selection and summary calculation, then pass the final payload to `_cached_json_response()`.

Catch `IrrigationRuntimeDataError` and return:

```python
raise HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Irrigation runtime statistics are unavailable",
) from exc
```

- [ ] **Step 4: Run API tests**

Run:

```powershell
python -m pytest backend/tests/test_irrigation.py -v
```

Expected: all irrigation route tests pass with unchanged response bodies and new cache headers.

- [ ] **Step 5: Commit the API migration**

```powershell
git add backend/routers/irrigation.py backend/tests/test_irrigation.py
git commit -m "perf: serve irrigation API from runtime shards"
```

---

## Task 5: Add proxy caching and production runtime configuration

**Files:**

- Modify: `nginx.conf`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `backend/tests/test_deployment_config.py`
- Modify: `README.md`
- Modify: `docs/deployment.md`

- [ ] **Step 1: Write failing deployment assertions**

Keep the two existing tile-cache assertions scoped to `/cog/` and `/api/tiles/`, then add exact statistics-location checks:

```python
def test_proxy_caches_irrigation_statistics_by_full_uri():
    nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")
    for endpoint in (
        "/api/irrigation/regions/averages",
        "/api/irrigation/series",
    ):
        block = nginx.split(f"location = {endpoint} {{", 1)[1].split("}", 1)[0]
        assert "proxy_cache tile_cache;" in block
        assert "proxy_cache_methods GET HEAD;" in block
        assert 'proxy_cache_key "$scheme$proxy_host$request_uri";' in block
        assert "proxy_cache_valid 200 1h;" in block
        assert "proxy_cache_lock on;" in block
        assert "add_header X-Stats-Cache $upstream_cache_status always;" in block
```

Extend the compose assertion:

```python
assert environment["IRRIGATION_RUNTIME_STATS_ROOT"] == (
    "/app/runtime-data/stats/irrigation_runtime"
)
```

Assert `.env.example`, `README.md`, and `docs/deployment.md` name the builder command and no longer require the monolithic file at runtime.

- [ ] **Step 2: Run deployment tests and confirm failures**

Run:

```powershell
python -m pytest backend/tests/test_deployment_config.py -v
```

Expected: missing stats cache locations and runtime-root environment setting fail.

- [ ] **Step 3: Add exact Nginx locations before `location /api/`**

Add one block per endpoint:

```nginx
location = /api/irrigation/regions/averages {
    limit_req zone=api_rate burst=20 nodelay;
    proxy_cache tile_cache;
    proxy_cache_methods GET HEAD;
    proxy_cache_key "$scheme$proxy_host$request_uri";
    proxy_cache_valid 200 1h;
    proxy_cache_lock on;
    proxy_cache_lock_timeout 60s;
    proxy_cache_lock_age 60s;
    proxy_pass http://backend:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;
    add_header X-Stats-Cache $upstream_cache_status always;
}
```

Add the same block for `/api/irrigation/series`. The full request URI keeps `level`, `countyId`, `regionId`, and `period` isolated in the cache key. Do not cache `404`, `422`, or `503`.

- [ ] **Step 4: Migrate deployment configuration and docs**

Replace the backend environment entry with:

```yaml
IRRIGATION_RUNTIME_STATS_ROOT: /app/runtime-data/stats/irrigation_runtime
```

Add to `.env.example`:

```dotenv
IRRIGATION_RUNTIME_STATS_ROOT=/app/runtime-data/stats/irrigation_runtime
```

Document this production sequence:

```powershell
python scripts/build_irrigation_runtime_stats.py
python scripts/build_irrigation_runtime_stats.py --check
docker compose up -d --build
```

State that the large source JSON and source vector chunks are offline build inputs, while `data/stats/irrigation_runtime/` is the tracked runtime artifact packaged/mounted into the backend.

- [ ] **Step 5: Run deployment tests**

Run:

```powershell
python -m pytest backend/tests/test_deployment_config.py -v
```

Expected: all deployment assertions pass and existing tile-cache assertions still cover exactly two tile routes.

- [ ] **Step 6: Commit deployment changes**

```powershell
git add nginx.conf docker-compose.yml .env.example backend/tests/test_deployment_config.py README.md docs/deployment.md
git commit -m "perf: cache irrigation statistics at the proxy"
```

---

## Task 6: Render county vectors before averages finish

**Files:**

- Modify: `frontend/src/pages/IrrigationPage.tsx`
- Modify: `frontend/src/test/App.test.tsx`

- [ ] **Step 1: Write a failing staged-loading test**

Use the existing `deferred()` helper and API mocks:

```typescript
it('renders county vectors while statistical coloring is still loading', async () => {
  const averages = deferred<IrrigationRegionAveragesResponse>()
  vi.mocked(api.getIrrigationVectorStatus).mockResolvedValue({
    level: 'county',
    available: true,
    url: '/api/irrigation/vectors/county',
    message: '县级矢量可用',
  })
  vi.mocked(api.getIrrigationVectorGeoJSON).mockResolvedValue(countyGeoJson)
  vi.mocked(api.getIrrigationRegionAverages).mockReturnValue(averages.promise)

  render(<App />)
  await userEvent.click(
    await screen.findByRole('button', { name: '区域统计' }),
  )

  expect(await screen.findByText('桥东区')).toBeInTheDocument()
  expect(screen.getByText('加载统计着色...')).toBeInTheDocument()

  averages.resolve({
    level: 'county',
    unit: '万m³',
    averages: [
      { regionId: '130502', name: '桥东区', average: 15 },
    ],
    legend: [],
  })
  await waitFor(() => {
    expect(screen.queryByText('加载统计着色...')).not.toBeInTheDocument()
  })
})
```

Add a second test that rejects the averages promise and verifies the county feature remains interactive while the UI reports uncolored statistics.

- [ ] **Step 2: Run the frontend test and confirm the coupled loading failure**

Run:

```powershell
cd frontend
npx vitest run src/test/App.test.tsx
```

Expected: the county vector or staged-loading message is not visible until averages settle.

- [ ] **Step 3: Separate vector and coloring state**

Add:

```typescript
const [countyVectorLoading, setCountyVectorLoading] = useState(false)
```

Keep requests concurrent but remove their `Promise.all` completion coupling:

```typescript
setCountyVectorLoading(true)
setCountyLegendStatus('loading')
void getIrrigationVectorStatus('county')
  .then(async (status) => {
    if (cancelled) return
    setVectorStatus(status)
    if (!status.available) return
    const vector = await loadVector('county')
    if (!cancelled) setCountyVector(vector)
  })
  .catch(() => {
    if (!cancelled) {
      setVectorStatus({
        level: 'county',
        available: false,
        url: null,
        message: '行政区矢量暂不可用',
      })
    }
  })
  .finally(() => {
    if (!cancelled) setCountyVectorLoading(false)
  })

void getIrrigationRegionAverages('county')
  .then((result) => {
    if (cancelled) return
    setCountyAverages(result.averages)
    setCountyLegend(result.legend)
    setCountyLegendStatus('ready')
  })
  .catch(() => {
    if (!cancelled) setCountyLegendStatus('error')
  })
```

Retain `adminStatsLoading` for township drill-down. In the sidebar, use:

```tsx
{regionLevel === 'county' && countyVectorLoading ? (
  <div className="loading">加载县级行政区...</div>
) : regionLevel === 'county' && countyLegendStatus === 'loading' ? (
  <div className="loading">加载统计着色...</div>
) : regionLevel === 'county' && countyLegendStatus === 'error' ? (
  <div className="chart-empty">行政区已加载，统计着色暂不可用</div>
) : regionLevel === 'township' && adminStatsLoading ? (
  <div className="loading">加载乡镇行政区统计数据...</div>
) : null}
```

Preserve the existing selected-region chart and empty-state branches around this status block.

- [ ] **Step 4: Run frontend tests, lint, and build**

Run:

```powershell
cd frontend
npx vitest run src/test/App.test.tsx
npm run lint
npm run build
```

Expected: tests pass, Oxlint reports no errors, and Vite build succeeds.

- [ ] **Step 5: Commit staged loading**

```powershell
git add frontend/src/pages/IrrigationPage.tsx frontend/src/test/App.test.tsx
git commit -m "perf: render irrigation vectors before statistics"
```

---

## Task 7: Generate real artifacts and enforce performance budgets

**Files:**

- Create: `data/stats/irrigation_runtime/manifest.json`
- Create: `data/stats/irrigation_runtime/averages/county.json`
- Create: `data/stats/irrigation_runtime/averages/township_by_county/*.json`
- Create: `data/stats/irrigation_runtime/series/county.json`
- Create: `data/stats/irrigation_runtime/series/township_index.json`
- Create: `data/stats/irrigation_runtime/series/township_by_source_code/*.json`
- Create: `scripts/benchmark_irrigation_runtime_stats.py`
- Create: `backend/tests/test_benchmark_irrigation_runtime_stats.py`

- [ ] **Step 1: Write failing benchmark-helper tests**

Test that timing and resident-memory helpers return non-negative numbers and that threshold violations return a non-zero CLI code:

```python
from scripts.benchmark_irrigation_runtime_stats import evaluate_budget


def test_evaluate_budget_accepts_target_measurements():
    assert evaluate_budget(
        cold_ms=250,
        hot_ms=75,
        rss_delta_mib=80,
        cold_limit_ms=300,
        hot_limit_ms=100,
        rss_limit_mib=100,
    ) == []


def test_evaluate_budget_reports_every_violation():
    assert evaluate_budget(
        cold_ms=301,
        hot_ms=101,
        rss_delta_mib=101,
        cold_limit_ms=300,
        hot_limit_ms=100,
        rss_limit_mib=100,
    ) == [
        "cold request 301.0 ms exceeds 300.0 ms",
        "hot request 101.0 ms exceeds 100.0 ms",
        "RSS delta 101.0 MiB exceeds 100.0 MiB",
    ]
```

- [ ] **Step 2: Run the benchmark test and confirm the module is missing**

Run:

```powershell
python -m pytest backend/tests/test_benchmark_irrigation_runtime_stats.py -v
```

Expected: collection fails because the benchmark module does not exist.

- [ ] **Step 3: Implement an isolated benchmark command**

The command must:

- point `backend.irrigation_runtime_stats.IRRIGATION_RUNTIME_STATS_ROOT` at `--runtime-root`;
- clear caches;
- collect the current process working set on Windows through `GetProcessMemoryInfo` and on Linux through `/proc/self/statm`;
- create one FastAPI `TestClient`;
- time a cold county averages request;
- time at least five hot requests and report the median;
- calculate RSS growth from before the cold request to after it;
- print JSON measurements;
- exit `1` when any approved threshold is exceeded.

Expose:

```python
def evaluate_budget(
    *,
    cold_ms: float,
    hot_ms: float,
    rss_delta_mib: float,
    cold_limit_ms: float,
    hot_limit_ms: float,
    rss_limit_mib: float,
) -> list[str]:
    failures = []
    if cold_ms > cold_limit_ms:
        failures.append(
            f"cold request {cold_ms:.1f} ms exceeds {cold_limit_ms:.1f} ms"
        )
    if hot_ms > hot_limit_ms:
        failures.append(
            f"hot request {hot_ms:.1f} ms exceeds {hot_limit_ms:.1f} ms"
        )
    if rss_delta_mib > rss_limit_mib:
        failures.append(
            f"RSS delta {rss_delta_mib:.1f} MiB exceeds {rss_limit_mib:.1f} MiB"
        )
    return failures
```

Use CLI defaults `300`, `100`, and `100` for the three limits.

- [ ] **Step 4: Run benchmark-helper tests**

Run:

```powershell
python -m pytest backend/tests/test_benchmark_irrigation_runtime_stats.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Generate and validate production artifacts**

Run from the repository root where the ignored source inputs are available:

```powershell
python scripts/build_irrigation_runtime_stats.py
python scripts/build_irrigation_runtime_stats.py --check
```

Inspect the generated manifest and require these source-derived values:

```text
countyCount: 2893
sourceTownshipCount: 43726
mappedTownshipCount: 43669
mappedTownshipPairCount: 46021
crossCountyTownshipCount: 2308
unmappedTownshipCount: 57
averageShardCount: 2865
```

Allow `seriesShardCount` to be whatever the builder derives, then verify it matches the number of generated township series shard files.

- [ ] **Step 6: Run the real performance gate**

Run:

```powershell
python scripts/benchmark_irrigation_runtime_stats.py --runtime-root data/stats/irrigation_runtime --cold-limit-ms 300 --hot-limit-ms 100 --rss-limit-mib 100
```

Expected: exit code `0`, cold at most 300 ms, hot median at most 100 ms, RSS delta below 100 MiB.

- [ ] **Step 7: Commit generated runtime data and benchmark**

```powershell
git add data/stats/irrigation_runtime scripts/benchmark_irrigation_runtime_stats.py backend/tests/test_benchmark_irrigation_runtime_stats.py
git commit -m "perf: publish irrigation runtime statistics"
```

---

## Task 8: Run complete verification and review the migration

**Files:**

- Review all files changed in Tasks 1–7
- Update: `task_plan.md`
- Update: `progress.md`

- [ ] **Step 1: Run the complete backend suite**

```powershell
python -m pytest backend/tests/ -v
```

Expected: all backend tests pass.

- [ ] **Step 2: Run the complete frontend suite**

```powershell
cd frontend
npx vitest run
npm run lint
npm run build
```

Expected: all tests pass, lint reports no errors, and build succeeds.

- [ ] **Step 3: Re-run artifact and performance validation**

```powershell
python scripts/build_irrigation_runtime_stats.py --check
python scripts/benchmark_irrigation_runtime_stats.py --runtime-root data/stats/irrigation_runtime --cold-limit-ms 300 --hot-limit-ms 100 --rss-limit-mib 100
```

Expected: no artifact drift and every performance gate passes.

- [ ] **Step 4: Review specification coverage**

Verify each approved design requirement:

- monolithic source absent from runtime routes and readiness;
- county and township average ownership follows vectors;
- each township series stored exactly once;
- 57 unmapped series IDs remain indexed;
- loaders have bounded caches and defensive copies;
- API cache validators preserve response contracts;
- Nginx caches only successful GET/HEAD responses by full URI;
- county vector rendering does not wait for averages;
- runtime artifacts are tracked and deployment docs use them.

- [ ] **Step 5: Scan for unfinished implementation markers and validate diffs**

Run:

```powershell
rg -n "TODO|FIXME|NotImplementedError|pass$" scripts/build_irrigation_runtime_stats.py backend/irrigation_runtime_stats.py scripts/benchmark_irrigation_runtime_stats.py
git diff --check
git status --short
```

Expected: no unfinished marker in the new implementation, no whitespace errors, and only intentional files remain changed.

- [ ] **Step 6: Commit final verification-only corrections**

If review required corrections, run the focused test first, then:

```powershell
git add backend frontend scripts data/stats/irrigation_runtime nginx.conf docker-compose.yml .env.example README.md docs
git commit -m "test: verify irrigation statistics performance"
```

Do not create an empty commit when no correction was needed.

