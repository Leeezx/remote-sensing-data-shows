"""Layers router — layer listing and time point retrieval."""

from fastapi import APIRouter, HTTPException, status

from backend.data_loader import get_layer, get_layer_times, get_layers

router = APIRouter(tags=["layers"])


@router.get("/layers")
def list_layers():
    """Return all available data layers with metadata."""
    return get_layers()


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
