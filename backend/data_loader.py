"""Shared data loading utilities for reading JSON data files."""

import json
import os
from pathlib import Path
from typing import Any

# Project root is two levels up from this file (backend/data_loader.py -> project/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_json(relative_path: str) -> Any:
    """Load and parse a JSON file relative to the project root."""
    filepath = PROJECT_ROOT / relative_path
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_layers() -> list[dict]:
    """Return the list of layer metadata objects."""
    return _load_json("data/metadata/layers.json")


def get_regions() -> list[dict]:
    """Return the list of region definitions."""
    return _load_json("data/stats/regions.json")


def get_area_stats() -> dict:
    """Return the area statistics dictionary (region -> layer -> time -> stats)."""
    return _load_json("data/stats/area_stats.json")


def get_layer_times(layer_id: str, resolution: str = "month") -> list[str]:
    """Return the time points for a given layer.

    Args:
        layer_id: Layer identifier (e.g. 'ssm').
        resolution: 'month' (default) or '8day'.
    """
    if resolution == "8day":
        return _load_json(f"data/series/{layer_id}_8day_times.json")
    return _load_json(f"data/series/{layer_id}_times.json")


def get_series(layer_id: str, resolution: str = "month") -> list[dict]:
    """Return the time series data for a given layer.

    Args:
        layer_id: Layer identifier (e.g. 'ssm').
        resolution: 'month' (default) or '8day'.
    """
    if resolution == "8day":
        return _load_json(f"data/series/{layer_id}_8day_series.json")
    return _load_json(f"data/series/{layer_id}_series.json")


def get_layer(layer_id: str) -> dict | None:
    """Return a single layer by ID, or None if not found."""
    layers = get_layers()
    for layer in layers:
        if layer["id"] == layer_id:
            return layer
    return None


def get_region(region_id: str) -> dict | None:
    """Return a single region by ID, or None if not found."""
    regions = get_regions()
    for region in regions:
        if region["id"] == region_id:
            return region
    return None


def get_region_series(layer_id: str, region_id: str | None = None, resolution: str = "month") -> list[dict]:
    """Return time series data for a layer, optionally filtered by region.

    If region_id is provided and per-region data exists, returns that region's data.
    Otherwise falls back to the default (North China Plain) series.

    Args:
        layer_id: Layer identifier (e.g. 'ssm').
        region_id: Optional region identifier for per-region data.
        resolution: 'month' (default) or '8day'.
    """
    if region_id:
        region_data = _load_json("data/series/region_series.json")
        if region_id in region_data and layer_id in region_data[region_id]:
            return region_data[region_id][layer_id]

    # Fallback to default series for the layer
    suffix = "8day_series.json" if resolution == "8day" else "series.json"
    return _load_json(f"data/series/{layer_id}_{suffix}")
