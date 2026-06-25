"""Spatial query router — point and area queries."""

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from backend.data_loader import get_area_stats, get_layer, get_regions

router = APIRouter(tags=["query"])


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


@router.get("/query/point")
def point_query(
    layerId: str = Query(...),
    time: str = Query(...),
    lng: float = Query(...),
    lat: float = Query(...),
):
    """Query a value at a specific point and time.

    Finds the nearest predefined region containing the point and returns
    the mean value from area statistics for that region/layer/time.
    """
    # Validate layer exists
    layer = get_layer(layerId)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layerId}' not found",
        )

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
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data available for layer '{layerId}' at time '{time}' in this region",
        )

    return {
        "layerId": layerId,
        "time": time,
        "lng": lng,
        "lat": lat,
        "value": region_stats["mean"],
        "unit": layer["unit"],
    }


@router.post("/query/area")
def area_query(body: AreaQueryRequest):
    """Query statistics for a geographic area.

    Accepts a GeoJSON geometry and returns aggregated statistics
    from the predefined area statistics data.
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Only Polygon geometry type is supported for area queries",
        )

    try:
        west, south, east, north = _get_bbox_from_polygon(body.geometry.coordinates)
    except (IndexError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid geometry coordinates",
        )

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
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No data available for layer '{body.layerId}' at time '{body.time}' in this region",
        )

    return {
        "mean": region_stats["mean"],
        "max": region_stats["max"],
        "min": region_stats["min"],
        "count": region_stats["count"],
    }
