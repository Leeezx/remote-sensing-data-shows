"""Bounded, version-aware access to irrigation runtime statistics."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from backend.runtime_config import IRRIGATION_RUNTIME_STATS_ROOT
from backend.township_chunks import county_code_from_id


class IrrigationRuntimeDataError(RuntimeError):
    """Raised when a required runtime artifact cannot be safely loaded."""


def _version(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
    except OSError as exc:
        raise IrrigationRuntimeDataError(
            f"irrigation runtime artifact unavailable: {path.name}"
        ) from exc
    return str(path), stat.st_mtime_ns, stat.st_size


def _read_object(path: str) -> dict:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IrrigationRuntimeDataError(
            f"invalid irrigation runtime artifact: {source.name}"
        ) from exc
    if not isinstance(payload, dict):
        raise IrrigationRuntimeDataError(
            f"irrigation runtime artifact must be an object: {source.name}"
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


def _manifest() -> dict:
    path = IRRIGATION_RUNTIME_STATS_ROOT / "manifest.json"
    manifest = _load_core(*_version(path))
    if manifest.get("schemaVersion") != 1:
        raise IrrigationRuntimeDataError(
            "unsupported irrigation runtime manifest schema"
        )
    return manifest


def load_region_averages(
    level: str,
    county_id: str | None = None,
) -> dict:
    """Load the requested precomputed averages payload."""
    _manifest()
    if level == "county":
        path = IRRIGATION_RUNTIME_STATS_ROOT / "averages" / "county.json"
        return copy.deepcopy(_load_core(*_version(path)))
    if level != "township":
        raise ValueError(f"unsupported irrigation region level: {level}")
    if county_id is None:
        raise ValueError("countyId is required for township averages")
    county_code = county_code_from_id(county_id)
    path = (
        IRRIGATION_RUNTIME_STATS_ROOT
        / "averages"
        / "township_by_county"
        / f"{county_code}.json"
    )
    return copy.deepcopy(_load_average_shard(*_version(path)))


def load_region_series_entry(
    level: str,
    region_id: str,
) -> tuple[str, dict] | None:
    """Load one region entry without retaining copies returned to callers."""
    manifest = _manifest()
    if level == "county":
        path = IRRIGATION_RUNTIME_STATS_ROOT / "series" / "county.json"
        payload = _load_core(*_version(path))
        regions = payload.get("regions")
        entry = regions.get(region_id) if isinstance(regions, dict) else None
        if not isinstance(entry, dict):
            return None
        return str(payload.get("unit", "万m³")), copy.deepcopy(entry)
    if level != "township":
        raise ValueError(f"unsupported irrigation region level: {level}")

    index_path = (
        IRRIGATION_RUNTIME_STATS_ROOT / "series" / "township_index.json"
    )
    index = _load_core(*_version(index_path))
    shard = index.get(region_id)
    if not isinstance(shard, str):
        return None
    shard_path = (
        IRRIGATION_RUNTIME_STATS_ROOT
        / "series"
        / "township_by_source_code"
        / f"{shard}.json"
    )
    entry = _load_series_shard(*_version(shard_path)).get(region_id)
    if not isinstance(entry, dict):
        return None
    unit = str(manifest.get("unit", "万m³"))
    return unit, copy.deepcopy(entry)


def clear_runtime_stats_caches() -> None:
    """Clear process-local runtime statistics caches."""
    _load_core.cache_clear()
    _load_average_shard.cache_clear()
    _load_series_shard.cache_clear()
