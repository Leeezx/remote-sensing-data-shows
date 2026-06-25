"""Static tile serving router — serves pre-generated raster tiles."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

router = APIRouter(tags=["tiles"])

# Project root is two levels up from routers/tiles.py → backend/routers/ → project/
TILES_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "tiles"


@router.get("/tiles/{layer}/{time}/{z}/{x}/{y}.png")
def serve_tile(layer: str, time: str, z: int, x: int, y: int):
    """Serve a pre-generated raster tile image."""
    tile_path = TILES_ROOT / layer / time / str(z) / str(x) / f"{y}.png"
    if not tile_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tile not found: {tile_path}",
        )
    return FileResponse(tile_path, media_type="image/png")
