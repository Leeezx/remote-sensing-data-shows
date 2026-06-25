"""CSV export router — CSV data export (researcher only)."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from backend.auth import require_role
from backend.data_loader import get_layer, get_region_series

router = APIRouter(tags=["export"])


@router.get("/export/csv", dependencies=[Depends(require_role("researcher"))])
def export_csv(
    layerId: str = Query(...),
    regionId: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    """Export time series data as CSV. Requires researcher role."""
    # Validate layer exists
    layer = get_layer(layerId)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layerId}' not found",
        )

    try:
        data = get_region_series(layerId, regionId)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Series data for layer '{layerId}' not found",
        )

    # Filter by date range
    if start or end:
        filtered = []
        for entry in data:
            t = entry["time"]
            if start and t < start:
                continue
            if end and t > end:
                continue
            filtered.append(entry)
        data = filtered

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["time", "value"])
    for entry in data:
        writer.writerow([entry["time"], entry["value"]])

    csv_content = output.getvalue()
    output.close()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={layerId}_series.csv"},
    )
