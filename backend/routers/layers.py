"""Layers router — layer listing and time point retrieval."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from backend.data_loader import get_layer, get_layer_times, get_layers
from backend.ssm_legend import get_dynamic_legend
from backend.ssm_time import ssm_time_to_cog_path

router = APIRouter(tags=["layers"])
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@router.get("/layers")
def list_layers():
    """Return all available data layers with metadata."""
    return get_layers()


@router.get("/layers/ssm/legend")
def ssm_legend(time: str):
    """Return the data-driven SSM legend for one strict time value."""
    try:
        cog_path = ssm_time_to_cog_path(
            PROJECT_ROOT / "data" / "rasters" / "ssm", time
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    layer = get_layer("ssm")
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSM layer metadata is missing",
        )
    base_legend = layer.get("legend")
    if not base_legend:
        raise RuntimeError("SSM layer legend is missing or empty")
    unit = layer.get("unit") or ""
    if not cog_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"COG file not found for time '{time}' "
                f"(looked for: {cog_path.name})"
            ),
        )
    return {
        "layerId": "ssm",
        "time": time,
        "unit": unit,
        "legend": get_dynamic_legend(cog_path, base_legend, unit),
    }


@router.get("/layers/{layer_id}/times")
def layer_times(layer_id: str, resolution: str = "month"):
    """Return available time points for a given layer.

    Query params:
        resolution: 'month' (default) or '8day' for 8-day composite data.
    """
    layer = get_layer(layer_id)
    if layer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Layer '{layer_id}' not found",
        )
    try:
        return get_layer_times(layer_id, resolution=resolution)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time data for layer '{layer_id}' not found",
        )
