"""Shared data loading utilities for reading JSON data files."""

import json
import os
from pathlib import Path
import re
from datetime import date, timedelta
from typing import Any

# Project root is two levels up from this file (backend/data_loader.py -> project/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IRRIGATION_ANNUAL_ROOT = Path(os.getenv("IRRIGATION_ANNUAL_ROOT", r"F:\IWU_RS_2025"))
IRRIGATION_8DAY_ROOT = Path(
    os.getenv(
        "IRRIGATION_8DAY_ROOT",
        r"F:\全国灌溉用水反演\数据2010-2013\全作物灌溉用水估计\IWU_calculate3",
    )
)
IRRIGATION_ANNUAL_COG_ROOT = Path(
    os.getenv(
        "IRRIGATION_ANNUAL_COG_ROOT",
        str(PROJECT_ROOT / "data" / "rasters" / "irrigation_annual"),
    )
)
IRRIGATION_8DAY_COG_ROOT = Path(
    os.getenv(
        "IRRIGATION_8DAY_COG_ROOT",
        str(PROJECT_ROOT / "data" / "rasters" / "irrigation_8day"),
    )
)

_IRRIGATION_ANNUAL_FILE = re.compile(r"^IWU_(?P<year>[0-9]{4})\.TIF$", re.IGNORECASE)
_IRRIGATION_8DAY_FILE = re.compile(
    r"^IWU_(?P<year>[0-9]{4})_(?P<period>[0-9]{1,3})\.tif$", re.IGNORECASE
)


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


def get_irrigation_layer() -> dict:
    """Return irrigation water layer metadata."""
    layer = _load_json("data/metadata/irrigation_layer.json")
    layer["tileTemplate"] = (
        "/data/irrigation-tiles/WebMercatorQuad/{z}/{x}/{y}.png?time={time}"
    )
    annual_times = get_irrigation_times("annual")
    if annual_times:
        layer["timeRange"] = {
            "start": annual_times[0],
            "end": annual_times[-1],
            "step": "annual",
        }
    return layer


def get_irrigation_times(resolution: str) -> list[str]:
    """Return available irrigation raster time points."""
    if resolution == "annual":
        if IRRIGATION_ANNUAL_ROOT.is_dir():
            years = []
            for path in IRRIGATION_ANNUAL_ROOT.iterdir():
                match = _IRRIGATION_ANNUAL_FILE.fullmatch(path.name)
                if match:
                    years.append(match.group("year"))
            return sorted(set(years))
        return _load_json("data/series/irrigation_annual_times.json")
    if resolution == "month":
        if IRRIGATION_8DAY_ROOT.is_dir():
            months = []
            for path in IRRIGATION_8DAY_ROOT.iterdir():
                match = _IRRIGATION_8DAY_FILE.fullmatch(path.name)
                if not match:
                    continue
                year = int(match.group("year"))
                period = int(match.group("period"))
                period_date = date(year, 1, 1) + timedelta(days=(period - 1) * 8)
                months.append(period_date.strftime("%Y-%m"))
            return sorted(set(months))
        return _load_json("data/series/irrigation_8day_times.json")
    raise ValueError("resolution must be 'annual' or 'month'")


def get_irrigation_regions() -> list[dict]:
    """Return irrigation administrative regions."""
    return _load_json("data/stats/irrigation_regions.json")


def get_irrigation_region_series() -> dict:
    """Return precomputed irrigation water totals by administrative region."""
    return _load_json("data/stats/irrigation_region_series.json")


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
