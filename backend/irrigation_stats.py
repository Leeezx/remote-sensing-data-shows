"""On-demand irrigation water statistics for administrative regions."""

from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import re

import numpy as np
import rasterio
from rasterio.errors import WindowError
from rasterio.features import geometry_mask, geometry_window
from rasterio.warp import transform_geom

from backend.data_loader import (
    IRRIGATION_8DAY_ROOT,
    IRRIGATION_ANNUAL_ROOT,
    PROJECT_ROOT,
    get_irrigation_times,
)
from backend.irrigation_legend import valid_irrigation_mask


_IRRIGATION_8DAY_FILE = re.compile(
    r"^IWU_(?P<year>[0-9]{4})_(?P<period>[0-9]{1,3})\.tif$", re.IGNORECASE
)
_CACHE_PATH = PROJECT_ROOT / "data" / "stats" / "irrigation_computed_series.json"


def _read_cache() -> dict:
    if not _CACHE_PATH.is_file():
        return {"unit": "万m³", "county": {}, "village": {}}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"unit": "万m³", "county": {}, "village": {}}


def _write_cache(cache: dict) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _sum_raster_geometry(raster_path: Path, geometry: dict) -> float:
    """Sum valid raster pixels inside one GeoJSON geometry."""
    with rasterio.open(raster_path) as src:
        raster_geometry = geometry
        if src.crs and str(src.crs) not in ("EPSG:4326", "OGC:CRS84"):
            raster_geometry = transform_geom("EPSG:4326", src.crs, geometry)
        try:
            window = geometry_window(src, [raster_geometry])
        except WindowError:
            return 0.0
        data = src.read(1, window=window)
        source_mask = src.read_masks(1, window=window)
        inside = geometry_mask(
            [raster_geometry],
            out_shape=data.shape,
            transform=src.window_transform(window),
            invert=True,
        )
        valid = valid_irrigation_mask(data, source_mask=source_mask, nodata=src.nodata) & inside
        if not np.any(valid):
            return 0.0
        return float(data[valid].sum(dtype="float64"))


def _annual_series(geometry: dict) -> list[dict]:
    series = []
    for year in get_irrigation_times("annual"):
        raster_path = IRRIGATION_ANNUAL_ROOT / f"IWU_{year}.TIF"
        if not raster_path.is_file():
            continue
        value = round(_sum_raster_geometry(raster_path, geometry), 1)
        series.append({"time": year, "value": value})
    return series


def _monthly_raster_groups() -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    if not IRRIGATION_8DAY_ROOT.is_dir():
        return groups
    for path in IRRIGATION_8DAY_ROOT.iterdir():
        match = _IRRIGATION_8DAY_FILE.fullmatch(path.name)
        if not match:
            continue
        year = int(match.group("year"))
        period = int(match.group("period"))
        period_date = date(year, 1, 1) + timedelta(days=(period - 1) * 8)
        groups[period_date.strftime("%Y-%m")].append(path)
    return groups


def _monthly_series(geometry: dict) -> list[dict]:
    series = []
    groups = _monthly_raster_groups()
    for month in get_irrigation_times("month"):
        value = sum(_sum_raster_geometry(path, geometry) for path in groups.get(month, []))
        series.append({"time": month, "value": round(value, 1)})
    return series


def compute_irrigation_region_series(
    level: str,
    region_id: str,
    region_name: str,
    geometry: dict,
    period: str,
) -> list[dict]:
    """Return cached or computed irrigation water totals for one region."""
    cache = _read_cache()
    level_cache = cache.setdefault(level, {})
    region_cache = level_cache.setdefault(
        region_id,
        {"name": region_name, "annual": None, "monthly": None},
    )
    if region_cache.get(period):
        return region_cache[period]

    if period == "annual":
        series = _annual_series(geometry)
    elif period == "monthly":
        series = _monthly_series(geometry)
    else:
        raise ValueError(f"Unsupported irrigation series period '{period}'")

    region_cache["name"] = region_name
    region_cache[period] = series
    _write_cache(cache)
    return series
