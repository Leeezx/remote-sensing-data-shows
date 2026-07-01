"""Spatial query router — point and area queries."""

from pathlib import Path

import rasterio
import rasterio.errors
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from pyproj import Transformer

from backend.data_loader import get_area_stats, get_layer, get_regions
from backend.raster_rendering import valid_data_mask
from backend.ssm_time import ssm_time_to_cog_path

router = APIRouter(tags=["query"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SSM_AREA_CHUNK_ROWS = 512


def _ssm_time_to_cog_path(time: str) -> Path:
    """Resolve a validated SSM time beneath the fixed raster root."""
    return ssm_time_to_cog_path(
        PROJECT_ROOT / "data" / "rasters" / "ssm", time
    )


def _validated_ssm_cog_path(time: str) -> Path:
    try:
        return _ssm_time_to_cog_path(time)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


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
    cog_path = _validated_ssm_cog_path(time)

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
            window = ((row, row + 1), (col, col + 1))
            val = src.read(1, window=window)
            source_mask = src.read_masks(1, window=window)
            value = float(val[0, 0])
            if not valid_data_mask(
                val, source_mask=source_mask, nodata=src.nodata
            )[0, 0]:
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
    cog_path = _validated_ssm_cog_path(time)

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
            count = 0
            total = 0.0
            minimum = None
            maximum = None
            for chunk_start in range(row_min, row_max, SSM_AREA_CHUNK_ROWS):
                chunk_end = min(chunk_start + SSM_AREA_CHUNK_ROWS, row_max)
                window = ((chunk_start, chunk_end), (col_min, col_max))
                data = src.read(1, window=window)
                source_mask = src.read_masks(1, window=window)
                mask = valid_data_mask(
                    data, source_mask=source_mask, nodata=src.nodata
                )
                valid = data[mask]
                if valid.size == 0:
                    continue
                count += int(valid.size)
                total += float(valid.sum(dtype="float64"))
                chunk_min = float(valid.min())
                chunk_max = float(valid.max())
                minimum = chunk_min if minimum is None else min(minimum, chunk_min)
                maximum = chunk_max if maximum is None else max(maximum, chunk_max)

            if count == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No valid data in the specified area",
                )
            return {
                "mean": total / count,
                "max": maximum,
                "min": minimum,
                "count": count,
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
