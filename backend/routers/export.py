"""CSV export router — CSV data export (researcher only)."""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from backend.auth import decode_access_token, require_role
from backend.data_loader import get_layer, get_region_series

router = APIRouter(tags=["export"])


async def get_user_from_header_or_query(request: Request) -> dict:
    """Extract user from Authorization header or `token` query parameter."""
    # Try Authorization header first (via Bearer)
    from backend.auth import get_current_user, security

    credentials = await security(request)
    if credentials is not None:
        return await get_current_user(credentials)

    # Fallback: check `token` query parameter (for <a> download links)
    token = request.query_params.get("token")
    if token:
        try:
            payload = decode_access_token(token)
            return {"username": payload["sub"], "role": payload["role"]}
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_researcher(request: Request) -> dict:
    """Require researcher role, checking both header and query token."""
    user = await get_user_from_header_or_query(request)
    if user["role"] != "researcher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user


@router.get("/export/csv")
async def export_csv(
    request: Request,
    layerId: str = Query(...),
    regionId: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    _user: dict = Depends(require_researcher),
):
    # ... rest of implementation remains the same ...
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
