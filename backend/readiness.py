"""Deployment readiness probes for separately supplied runtime data."""

import json
from functools import lru_cache
from pathlib import Path

from backend.runtime_config import (
    COUNTY_VECTOR_PATH,
    IRRIGATION_8DAY_ROOT,
    IRRIGATION_ANNUAL_ROOT,
    IRRIGATION_REGION_SERIES_PATH,
    RASTER_ROOT,
    TOWNSHIP_CHUNK_ROOT,
)


@lru_cache(maxsize=8)
def _cached_json_probe(path: str, mtime_ns: int, size: int) -> bool:
    del mtime_ns, size
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return isinstance(json.load(handle), dict)
    except (OSError, json.JSONDecodeError):
        return False


def probe_json_object(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return stat.st_size > 0 and _cached_json_probe(
        str(path), stat.st_mtime_ns, stat.st_size
    )


def required_raster_roots() -> list[tuple[str, Path]]:
    roots = [
        (identifier, RASTER_ROOT / identifier)
        for identifier in (
            "ssm",
            "et",
            "sm_10cm",
            "sm_30cm",
            "sm_60cm",
            "sm_100cm",
        )
    ]
    roots.extend(
        (
            ("irrigation_annual", IRRIGATION_ANNUAL_ROOT),
            ("irrigation_8day", IRRIGATION_8DAY_ROOT),
        )
    )
    return roots


def _contains_tiff(root: Path) -> bool:
    return root.is_dir() and any(
        path.is_file() and path.suffix.lower() in {".tif", ".tiff"}
        for path in root.iterdir()
    )


def collect_readiness_failures() -> list[str]:
    failures = []
    if not probe_json_object(IRRIGATION_REGION_SERIES_PATH):
        failures.append("irrigation_region_series")
    if not all(
        COUNTY_VECTOR_PATH.with_suffix(suffix).is_file()
        for suffix in (".shp", ".shx", ".dbf")
    ):
        failures.append("county_vector")
    if not (TOWNSHIP_CHUNK_ROOT / "manifest.json").is_file():
        failures.append("township_chunks")
    failures.extend(
        identifier
        for identifier, root in required_raster_roots()
        if not _contains_tiff(root)
    )
    return failures
