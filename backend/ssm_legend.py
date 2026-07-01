"""Data-driven legend thresholds for soil-surface-moisture rasters."""

from functools import lru_cache
from pathlib import Path
import threading

import numpy as np
import rasterio

from backend.raster_rendering import valid_data_mask


_CACHE_LOCKS = tuple(threading.Lock() for _ in range(64))


def _copy_legend(legend):
    return [dict(item) for item in legend]


def build_dynamic_legend(values, base_legend, unit, source_mask=None, nodata=None):
    """Build six evenly spaced legend stops from valid raster values."""
    base_legend = list(base_legend)
    if len(base_legend) != 6:
        return _copy_legend(base_legend)

    values = np.asarray(values)
    valid = valid_data_mask(values, source_mask=source_mask, nodata=nodata)
    valid_values = values[valid]
    if valid_values.size == 0:
        return _copy_legend(base_legend)

    low, high = np.percentile(valid_values, [2, 98])
    if not np.all(np.isfinite((low, high))) or low >= high:
        return _copy_legend(base_legend)

    stops = np.linspace(low, high, 6)
    if not np.all(np.isfinite(stops)):
        return _copy_legend(base_legend)
    return [
        {
            "value": float(value),
            "color": item["color"],
            "label": f"{value:.3f} {unit}".strip(),
        }
        for value, item in zip(stops, base_legend)
    ]


def _read_dynamic_legend(path):
    with rasterio.open(path) as dataset:
        return dataset.read(1), dataset.read_masks(1), dataset.nodata


def _immutable_legend(legend):
    return tuple((item["value"], item["color"], item["label"]) for item in legend)


@lru_cache(maxsize=64)
def _cached_dynamic_legend(resolved_path, mtime_ns, base_signature, unit):
    del mtime_ns
    values, source_mask, nodata = _read_dynamic_legend(resolved_path)
    base_legend = [
        {"value": value, "color": color, "label": label}
        for value, color, label in base_signature
    ]
    return _immutable_legend(
        build_dynamic_legend(
            values,
            base_legend,
            unit,
            source_mask=source_mask,
            nodata=nodata,
        )
    )


def get_dynamic_legend(cog_path: Path, base_legend, unit):
    """Return a cached data-driven legend as fresh mutable dictionaries."""
    resolved_path = Path(cog_path).resolve()
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
        cached = _cached_dynamic_legend(*cache_key)
    return [
        {"value": value, "color": color, "label": label}
        for value, color, label in cached
    ]
