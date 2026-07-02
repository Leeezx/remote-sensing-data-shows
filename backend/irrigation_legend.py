"""Irrigation-specific legend and validity helpers."""

from functools import lru_cache
import json
from pathlib import Path
import threading

import numpy as np
import rasterio

from backend.data_loader import PROJECT_ROOT
from backend.raster_rendering import valid_data_mask
from backend.ssm_legend import build_dynamic_legend

_CACHE_LOCKS = tuple(threading.Lock() for _ in range(64))
_LEGEND_CACHE_PATH = PROJECT_ROOT / "data" / "stats" / "irrigation_legends.json"
_legend_disk_cache: dict | None = None


def _load_legend_disk_cache() -> dict:
    """Load persisted legend thresholds from disk (lazy, cached in module)."""
    global _legend_disk_cache
    if _legend_disk_cache is not None:
        return _legend_disk_cache
    if not _LEGEND_CACHE_PATH.is_file():
        _legend_disk_cache = {}
        return _legend_disk_cache
    try:
        _legend_disk_cache = json.loads(_LEGEND_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _legend_disk_cache = {}
    return _legend_disk_cache


def _save_legend_disk_cache(disk_cache: dict) -> None:
    """Write the legend cache to disk."""
    global _legend_disk_cache
    _legend_disk_cache = disk_cache
    _LEGEND_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LEGEND_CACHE_PATH.write_text(
        json.dumps(disk_cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def valid_irrigation_mask(values, source_mask=None, nodata=None):
    """Return valid irrigation pixels, excluding negative water volumes."""
    values = np.asarray(values)
    return valid_data_mask(values, source_mask=source_mask, nodata=nodata) & (values >= 0)


def build_irrigation_dynamic_legend(values, base_legend, unit, source_mask=None, nodata=None):
    """Build a data-driven irrigation legend from non-negative valid pixels."""
    values = np.asarray(values)
    valid = valid_irrigation_mask(values, source_mask=source_mask, nodata=nodata)
    masked_values = np.where(valid, values, np.nan)
    return build_dynamic_legend(masked_values, base_legend, unit)


def _read_irrigation_raster(path):
    """Read full raster band, mask, and nodata for legend computation."""
    with rasterio.open(path) as dataset:
        return dataset.read(1), dataset.read_masks(1), dataset.nodata


def _immutable_legend(legend):
    """Convert legend dicts to hashable tuples for lru_cache."""
    return tuple((item["value"], item["color"], item["label"]) for item in legend)


@lru_cache(maxsize=64)
def _cached_irrigation_legend(resolved_path, mtime_ns, base_signature, unit):
    """Cached legend computation — only recomputes when raster file changes."""
    del mtime_ns
    values, source_mask, nodata = _read_irrigation_raster(resolved_path)
    base_legend = [
        {"value": value, "color": color, "label": label}
        for value, color, label in base_signature
    ]
    return _immutable_legend(
        build_irrigation_dynamic_legend(
            values,
            base_legend,
            unit,
            source_mask=source_mask,
            nodata=nodata,
        )
    )


def get_irrigation_dynamic_legend(raster_path: Path, base_legend, unit, time: str = ""):
    """Return a cached irrigation dynamic legend for one raster.

    Checks a persistent disk cache first (keyed by *time*), then the
    in-memory LRU cache, and only reads the full raster as a last resort.
    After a fresh computation the result is persisted to disk so it
    survives server restarts and is available instantly on next request.
    """
    # 1. Persistent disk cache (survives restarts) -----------------------
    if time:
        disk_cache = _load_legend_disk_cache()
        if time in disk_cache:
            return disk_cache[time]

    # 2. In-memory LRU cache (fastest path for same process) -------------
    resolved_path = Path(raster_path).resolve()
    base_signature = tuple(
        (item.get("value"), item.get("color"), item.get("label"))
        for item in base_legend
    )
    cache_key = (
        str(resolved_path),
        resolved_path.stat().st_mtime_ns,
        base_signature,
        unit,
    )
    cache_lock = _CACHE_LOCKS[hash(cache_key) % len(_CACHE_LOCKS)]
    with cache_lock:
        cached = _cached_irrigation_legend(*cache_key)
    legend = [
        {"value": value, "color": color, "label": label}
        for value, color, label in cached
    ]

    # 3. Persist to disk for future restarts -----------------------------
    if time:
        disk_cache = _load_legend_disk_cache()
        if time not in disk_cache:
            disk_cache[time] = legend
            _save_legend_disk_cache(disk_cache)

    return legend
