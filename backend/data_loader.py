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


def get_layer_times(layer_id: str) -> list[str]:
    """Return the time points for a given layer."""
    return _load_json(f"data/series/{layer_id}_times.json")


def get_series(layer_id: str) -> list[dict]:
    """Return the time series data for a given layer."""
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
