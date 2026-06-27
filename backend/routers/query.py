"""Spatial query router — point and area queries."""

import math
from pathlib import Path

import rasterio
import rasterio.errors
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from pyproj import Transformer

from backend.data_loader import get_area_stats, get_layer, get_regions

router = APIRouter(tags=["query"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ===== SSM COG filename mapping =====
# COG files are named YYYY_NN_cog.tif (e.g., 2010_05_cog.tif)
# where NN is the 8-day period index (1-46) within the year.
# The 8-day times in ssm_8day_times.json use date strings (e.g., "2010-02-02").
# This function maps from either format to the correct COG filename.

def _ssm_time_to_cog_path(time: str) -> Path:
    """Convert a time string to the corresponding SSM COG file path.

    Supports two formats:
      - Period index: "YYYY_NN" (e.g., "2010_05") — maps directly
      - 8-day date:   "YYYY-MM-DD" (e.g., "2010-02-02") — computes period index
      - Monthly:      "YYYY-MM" (e.g., "2010-02") — uses first 8-day period of month
    """
    # Already in YYYY_NN format — direct COG filename
    if "_" in time:
        cog_name = f"{time}_cog.tif"
    elif len(time) == 10:
        # 8-day date: "YYYY-MM-DD"
        from datetime import date
        year_s = int(time[:4])
        month_s = int(time[5:7])
        day_s = int(time[8:10])
        d = date(year_s, month_s, day_s)
        start = date(year_s, 1, 1)
        period = (d - start).days // 8 + 1
        cog_name = f"{year_s}_{period:02d}_cog.tif"
    elif len(time) == 7:
        # Monthly: "YYYY-MM" — use the 8-day period closest to mid-month
        from datetime import date
        year_s = int(time[:4])
        month_s = int(time[5:7])
        d = date(year_s, month_s, 15)
        start = date(year_s, 1, 1)
        period = (d - start).days // 8 + 1
        cog_name = f"{year_s}_{period:02d}_cog.tif"
    else:
        # Unknown format — try as-is
        cog_name = f"{time}_cog.tif"

    return PROJECT_ROOT / "data" / "rasters" / "ssm" / cog_name


class GeoJSONGeometry(BaseModel):
    type: str
    coordinates: list


class AreaQueryRequest(BaseModel):
    layerId: str
    time: str
    geometry: GeoJSONGeometry


def _find_region_for_point(lng: float, lat: float) -> dict | None:
    """Find the predefined region that contains the given point."""
    for region in get_regions():
        b = region["bounds"]
        if b["west"] <= lng <= b["east"] and b["south"] <= lat <= b["north"]:
            return region
    return None


def _find_regions_for_bbox(
    west: float, south: float, east: float, north: float
) -> list[dict]:
    """Find all predefined regions that intersect with the given bounding box."""
    matching = []
    for region in get_regions():
        b = region["bounds"]
        # Check if bounding boxes intersect
        if b["west"] <= east and b["east"] >= west and b["south"] <= north and b["north"] >= south:
            matching.append(region)
    return matching


def _get_bbox_from_polygon(coordinates: list) -> tuple[float, float, float, float]:
    """Compute bounding box from polygon exterior ring coordinates."""
    ring = coordinates[0]  # exterior ring
    lngs = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    return min(lngs), min(lats), max(lngs), max(lats)


def _query_point_SSM(layer: dict, time: str, lng: float, lat: float) -> dict:
    """Real-time point query for SSM layer using rasterio."""
    import numpy as np

    cog_path = _ssm_time_to_cog_path(time)

    if not cog_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"COG file not found for time '{time}' (looked for: {cog_path.name})",
        )

    try:
        with rasterio.open(cog_path) as src:
            # EPSG:4326 → raster CRS (same, but ensure correctness)
            transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
            x, y = transformer.transform(lng, lat)
            row, col = src.index(x, y)
            if row < 0 or row >= src.height or col < 0 or col >= src.width:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Point is outside the raster extent",
                )
            val = src.read(1, window=((row, row + 1), (col, col + 1)))
            value = float(val[0, 0])
            if math.isnan(value):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No valid data at this point",
                )
    except rasterio.errors.RasterioIOError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read raster: {e}",
        )

    return {
        "layerId": layer["id"],
        "time": time,
        "lng": lng,
        "lat": lat,
        "value": value,
        "unit": layer["unit"],
    }


def _query_area_SSM(layer: dict, time: str, west: float, south: float, east: float, north: float) -> dict:
    """Real-time area query for SSM layer using rasterio."""
    import numpy as np

    cog_path = _ssm_time_to_cog_path(time)

    if not cog_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"COG file not found for time '{time}' (looked for: {cog_path.name})",
        )

    try:
        with rasterio.open(cog_path) as src:
            # WGS84 bbox → raster row/col indices
            row_min, col_min = src.index(west, north)
            row_max, col_max = src.index(east, south)
            # Clamp to valid range
            row_min, row_max = max(0, row_min), min(src.height, row_max + 1)
            col_min, col_max = max(0, col_min), min(src.width, col_max + 1)
            if row_min >= row_max or col_min >= col_max:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Area is outside the raster extent",
                )
            data = src.read(1, window=((row_min, row_max), (col_min, col_max)))
            valid = data[~np.isnan(data)]
            if src.nodata is not None:
                valid = valid[valid != src.nodata]
            if valid.size == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No valid data in the specified area",
                )
            return {
                "mean": float(valid.mean()),
                "max": float(valid.max()),
                "min": float(valid.min()),
                "count": int(valid.size),
            }
    except rasterio.errors.RasterioIOError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read raster: {e}",
        )


@router.get("/query/point")
def point_query(
    layerId: str = Query(...),
    time: str = Query(...),
    lng: float = Query(...),
    lat: float = Query(...),
):
    """Query a value at a specific point and time.

    For SSM layer: reads the actual pixel value from the COG file.
    For other layers: returns the nearest region's pre-computed statistics.
    """
    # Validate layer exists
    layer = get_layer(layerId)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layerId}' not found",
        )

    # ---- SSM layer: use rasterio to read pixel from COG file ----
    if layerId == "ssm":
        return _query_point_SSM(layer, time, lng, lat)

    # ---- Other layers: fall through to JSON stats lookup ----
    # Find region containing the point
    region = _find_region_for_point(lng, lat)
    if region is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No data for the specified coordinates",
        )

    stats = get_area_stats()
    try:
        region_stats = stats[region["id"]][layerId][time]
        value = region_stats["mean"]
    except KeyError:
        # Fallback to series data for layers not in area_stats
        from backend.data_loader import get_series as _get_series
        try:
            series = _get_series(layerId)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data available for layer '{layerId}'",
            )
        value = None
        for entry in series:
            if entry["time"] == time:
                value = entry["value"]
                break
        if value is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data available for layer '{layerId}' at time '{time}' in this region",
            )

    return {
        "layerId": layerId,
        "time": time,
        "lng": lng,
        "lat": lat,
        "value": value,
        "unit": layer["unit"],
    }


@router.post("/query/area")
def area_query(body: AreaQueryRequest):
    """Query statistics for a geographic area.

    For SSM layer: reads actual pixels from the COG file and computes stats.
    For other layers: returns pre-computed area statistics from JSON.
    """
    # Validate layer exists
    layer = get_layer(body.layerId)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{body.layerId}' not found",
        )

    # Compute bounding box from geometry
    if body.geometry.type != "Polygon":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only Polygon geometry type is supported for area queries",
        )

    try:
        west, south, east, north = _get_bbox_from_polygon(body.geometry.coordinates)
    except (IndexError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid geometry coordinates",
        )

    # ---- SSM layer: use rasterio to read and compute stats from COG ----
    if body.layerId == "ssm":
        return _query_area_SSM(layer, body.time, west, south, east, north)

    # ---- Other layers: fall through to JSON stats lookup ----
    # Find intersecting regions
    regions = _find_regions_for_bbox(west, south, east, north)
    if not regions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No data for the specified area",
        )

    # Return stats for the first matching region (MVP simplification)
    region = regions[0]
    stats = get_area_stats()
    try:
        region_stats = stats[region["id"]][body.layerId][body.time]
        return {
            "mean": region_stats["mean"],
            "max": region_stats["max"],
            "min": region_stats["min"],
            "count": region_stats["count"],
        }
    except KeyError:
        # Fallback to series data for layers not in area_stats
        from backend.data_loader import get_series as _get_series
        try:
            series = _get_series(body.layerId)
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data available for layer '{body.layerId}'",
            )
        val = None
        for entry in series:
            if entry["time"] == body.time:
                val = entry["value"]
                break
        if val is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No data available for layer '{body.layerId}' at time '{body.time}' in this region",
            )
        return {"mean": val, "max": val, "min": val, "count": 1}
