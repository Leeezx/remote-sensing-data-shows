"""Regions router — region definitions listing."""

from fastapi import APIRouter

from backend.data_loader import get_regions

router = APIRouter(tags=["regions"])


@router.get("/regions")
def list_regions():
    """Return all available geographic regions."""
    return get_regions()
