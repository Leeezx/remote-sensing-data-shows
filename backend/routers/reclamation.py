"""Cached reclamation map artifact endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse

from backend.reclamation_data import choose_representation, load_manifest, region_ids


router = APIRouter(tags=["reclamation"])
RECLAMATION_ROOT = Path(__file__).resolve().parents[2] / "data" / "reclamation"


def _manifest_or_http_error() -> None:
    try:
        load_manifest(RECLAMATION_ROOT)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reclamation artifacts are unavailable",
        ) from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reclamation artifact manifest is invalid",
        ) from exc


def _file_response(relative_path: Path, accept_encoding: str, cache_control: str):
    try:
        path, representation_headers = choose_representation(
            RECLAMATION_ROOT,
            relative_path,
            accept_encoding,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reclamation artifact was not found",
        ) from exc
    return FileResponse(
        path,
        media_type="application/json",
        headers={**representation_headers, "Cache-Control": cache_control},
    )


@router.get("/reclamation/regions")
def reclamation_regions(accept_encoding: str = Header(default="")):
    """Return the cached reclamation overview artifact."""
    _manifest_or_http_error()
    return _file_response(Path("overview.json"), accept_encoding, "public, max-age=300")


@router.get("/reclamation/points/{region_id}")
def reclamation_points(region_id: str, accept_encoding: str = Header(default="")):
    """Return one cached reclamation point artifact."""
    _manifest_or_http_error()
    try:
        known_regions = region_ids(RECLAMATION_ROOT)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reclamation artifact manifest is invalid",
        ) from exc
    if region_id not in known_regions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reclamation region was not found",
        )
    return _file_response(
        Path("points") / f"{region_id}.json",
        accept_encoding,
        "public, max-age=86400",
    )
