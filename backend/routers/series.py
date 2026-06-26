"""Time series router — time series data retrieval."""

from fastapi import APIRouter, HTTPException, Query, status

from backend.data_loader import get_layer, get_region_series

router = APIRouter(tags=["series"])


@router.get("/series")
def list_series(
    layerId: str = Query(...),
    regionId: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    resolution: str = Query(default="month"),
):
    """Return time series data for a layer and optionally a region.

    When regionId is provided, returns per-region series data.
    Falls back to default (North China Plain) series if region not found.
    Supports date range filtering with start/end parameters.

    Query params:
        resolution: 'month' (default) or '8day'.
    """
    # Validate layer exists
    layer = get_layer(layerId)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layerId}' not found",
        )

    try:
        data = get_region_series(layerId, regionId, resolution=resolution)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Series data for layer '{layerId}' not found",
        )

    # Filter by date range if specified
    if start or end:
        filtered = []
        for entry in data:
            t = entry["time"]
            if start and t < start:
                continue
            if end and t > end:
                continue
            filtered.append(entry)
        return filtered

    return data
