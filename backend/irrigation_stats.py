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
        return {"unit": "万m³", "county": {}, "township": {}}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"unit": "万m³", "county": {}, "township": {}}


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


def get_irrigation_region_averages(level: str, county_id: str | None = None) -> dict:
    """Return per-region multi-year average irrigation water and a dynamic legend.

    Computes the mean of each region's annual series values, then builds a
    6-stop legend from the distribution of those means using the same
    percentile method as the raster dynamic legend.
    """
    import numpy as np

    from backend.data_loader import (
        get_irrigation_layer,
        get_irrigation_regions,
        get_irrigation_region_series,
    )
    from backend.ssm_legend import build_dynamic_legend

    series_data = get_irrigation_region_series()
    unit = series_data.get("unit", "万m³")
    regions = get_irrigation_regions()
    level_regions = [r for r in regions if r["level"] == level]
    if level == "township":
        if county_id is None:
            raise ValueError("countyId is required for township averages")
        from backend.township_chunks import county_code_from_id

        county_code = county_code_from_id(county_id)
        level_regions = [
            region
            for region in level_regions
            if str(region.get("id", "")).startswith(county_code)
        ]
    level_series = series_data.get(level, {})

    averages = []
    for region in level_regions:
        region_id = region["id"]
        region_name = region["name"]
        region_entry = level_series.get(region_id, {})
        annual_series = region_entry.get("annual") if isinstance(region_entry, dict) else None
        if annual_series and len(annual_series) > 0:
            avg = sum(float(p["value"]) for p in annual_series) / len(annual_series)
            averages.append({
                "regionId": region_id,
                "name": region_name,
                "average": round(avg, 1),
            })
        else:
            averages.append({
                "regionId": region_id,
                "name": region_name,
                "average": None,
            })

    # Build legend from valid averages
    valid_averages = np.array([a["average"] for a in averages if a["average"] is not None])
    layer = get_irrigation_layer()
    base_legend = layer.get("legend", [])
    if valid_averages.size > 0 and base_legend:
        legend = build_dynamic_legend(valid_averages, base_legend, unit)
    else:
        legend = [dict(item) for item in base_legend]

    return {
        "level": level,
        "unit": unit,
        "averages": averages,
        "legend": legend,
    }
