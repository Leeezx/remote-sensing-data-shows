"""Cached water-demand map artifact endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse

from backend.water_demand_data import (
    POINTS_MEDIA_TYPE,
    choose_representation,
    load_manifest,
)


router = APIRouter(tags=["water-demand"])
WATER_DEMAND_ROOT = Path(__file__).resolve().parents[2] / "data" / "water_demand"


def _manifest_or_http_error() -> None:
    try:
        load_manifest(WATER_DEMAND_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Water-demand artifacts are unavailable",
        ) from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Water-demand artifact manifest is invalid",
        ) from exc


def _file_response(
    relative_name: str,
    media_type: str,
    accept_encoding: str,
    cache_control: str,
):
    try:
        path, representation_headers = choose_representation(
            WATER_DEMAND_ROOT,
            relative_name,
            accept_encoding,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Water-demand artifact was not found",
        ) from exc
    return FileResponse(
        path,
        media_type=media_type,
        headers={**representation_headers, "Cache-Control": cache_control},
    )


@router.get("/water-demand/overview")
def water_demand_overview(accept_encoding: str = Header(default="")):
    """Return the demo region, China outline, legend and metric metadata."""
    _manifest_or_http_error()
    return _file_response(
        "overview.json",
        "application/json",
        accept_encoding,
        "public, max-age=300",
    )


@router.get("/water-demand/points")
def water_demand_points(accept_encoding: str = Header(default="")):
    """Return the compact binary point transport for the demo region."""
    _manifest_or_http_error()
    return _file_response(
        "points.bin",
        POINTS_MEDIA_TYPE,
        accept_encoding,
        "public, max-age=86400",
    )
