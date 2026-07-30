"""Irrigation water router — raster metadata and administrative statistics."""

import hashlib
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from backend.data_loader import (
    IRRIGATION_8DAY_ROOT,
    IRRIGATION_ANNUAL_ROOT,
    IRRIGATION_ANNUAL_COG_ROOT,
    IRRIGATION_8DAY_COG_ROOT,
    get_irrigation_layer,
    get_irrigation_regions,
    get_irrigation_times,
)
from backend.irrigation_runtime_stats import (
    IrrigationRuntimeDataError,
    load_region_averages,
    load_region_series_entry,
)
from backend.irrigation_time import irrigation_time_to_cog_path, irrigation_time_to_path
from backend.irrigation_legend import get_irrigation_dynamic_legend
from backend.runtime_config import COUNTY_VECTOR_PATH, TOWNSHIP_CHUNK_ROOT
from backend.shapefile_geojson import read_shapefile_geojson
from backend.township_chunks import (
    MAX_TOWNSHIP_CHUNK_BYTES,
    MAX_TOWNSHIP_FEATURES,
    load_township_chunk,
    township_chunk_path,
)

router = APIRouter(tags=["irrigation"])

RegionLevel = Literal["county", "township"]
SeriesPeriod = Literal["annual", "monthly"]
RasterResolution = Literal["annual", "month"]


def _cached_json_response(request: Request, payload: dict) -> Response:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    etag = f'"{hashlib.sha256(body).hexdigest()}"'
    headers = {
        "Cache-Control": "public, max-age=3600",
        "ETag": etag,
    }
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=headers,
        )
    return Response(
        content=body,
        media_type="application/json",
        headers=headers,
    )


def _find_region(region_id: str, level: RegionLevel) -> dict | None:
    for region in get_irrigation_regions():
        if region["id"] == region_id and region["level"] == level:
            return region
    return None


@router.get("/irrigation/layer")
def irrigation_layer():
    """Return irrigation water raster layer metadata."""
    return get_irrigation_layer()


@router.get("/irrigation/times")
def irrigation_times(resolution: RasterResolution = Query(default="annual")):
    """Return available raster time points for annual or 8-day irrigation data."""
    try:
        return get_irrigation_times(resolution)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get("/irrigation/legend")
def irrigation_legend(time: str):
    """Return a data-driven legend for one irrigation raster time."""
    try:
        raster_path = irrigation_time_to_cog_path(
            IRRIGATION_ANNUAL_ROOT,
            IRRIGATION_ANNUAL_COG_ROOT,
            IRRIGATION_8DAY_ROOT,
            IRRIGATION_8DAY_COG_ROOT,
            time,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if not raster_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Irrigation raster not found for time '{time}' "
                f"(looked for: {raster_path.name})"
            ),
        )
    layer = get_irrigation_layer()
    return {
        "layerId": "irrigation_water",
        "time": time,
        "unit": layer["unit"],
        "legend": get_irrigation_dynamic_legend(
            raster_path,
            layer["legend"],
            layer["unit"],
            time=time,
        ),
    }


@router.get("/irrigation/vectors")
def irrigation_vector_status(level: RegionLevel = Query(...)):
    """Return availability information for administrative vector overlays."""
    if level == "county":
        return {
            "level": level,
            "available": COUNTY_VECTOR_PATH.is_file(),
            "url": "/api/irrigation/vectors/county",
            "message": "县级行政区矢量可用"
            if COUNTY_VECTOR_PATH.is_file()
            else "县级行政区矢量文件不存在",
        }
    chunks_available = (TOWNSHIP_CHUNK_ROOT / "manifest.json").is_file()
    return {
        "level": level,
        "available": chunks_available,
        "url": "/api/irrigation/vectors/township?countyId={countyId}"
        if chunks_available
        else None,
        "message": "请先在地图上选择县域，再加载该县乡镇"
        if chunks_available
        else "乡镇矢量分片尚未生成",
    }


@router.get("/irrigation/vectors/county")
def county_vector_geojson():
    """Return county administrative boundaries as GeoJSON."""
    if not COUNTY_VECTOR_PATH.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="County vector file is not configured",
        )
    return read_shapefile_geojson(COUNTY_VECTOR_PATH)


@router.get("/irrigation/vectors/township")
def township_vector_geojson(countyId: str = Query(...)):
    """Return one county-scoped township GeoJSON chunk."""
    try:
        chunk_path = township_chunk_path(TOWNSHIP_CHUNK_ROOT, countyId)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if not chunk_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "township_vector_not_found",
                "message": "该县暂无乡镇矢量",
                "countyId": countyId,

            },
        )
    chunk_bytes = chunk_path.stat().st_size
    try:
        data = load_township_chunk(TOWNSHIP_CHUNK_ROOT, countyId)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Township vector chunk is unreadable",
        ) from exc
    feature_count = len(data.get("features", []))
    if chunk_bytes > MAX_TOWNSHIP_CHUNK_BYTES or feature_count > MAX_TOWNSHIP_FEATURES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Township vector chunk exceeds the configured delivery limits",
        )
    return FileResponse(
        chunk_path,
        media_type="application/geo+json",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Chunk-Bytes": str(chunk_bytes),
            "X-Feature-Count": str(feature_count),
        },
    )


@router.get("/irrigation/regions/averages")
def irrigation_region_averages(
    request: Request,
    level: RegionLevel = Query(...),
    countyId: str | None = Query(default=None),
):
    """Return per-region annual-average irrigation water and a choropleth legend."""
    if level == "township" and countyId is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="countyId is required for township averages",
        )
    try:
        payload = load_region_averages(level, county_id=countyId)
    except IrrigationRuntimeDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Irrigation runtime statistics are unavailable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return _cached_json_response(request, payload)


@router.get("/irrigation/regions")
def irrigation_regions(level: RegionLevel | None = Query(default=None)):
    """Return county and township administrative units for irrigation statistics."""
    regions = get_irrigation_regions()
    if level is None:
        return regions
    return [region for region in regions if region["level"] == level]


@router.get("/irrigation/series")
def irrigation_series(
    request: Request,
    level: RegionLevel = Query(...),
    regionId: str = Query(...),
    period: SeriesPeriod = Query(default="annual"),
):
    """Return precomputed irrigation water totals for one administrative region."""
    try:
        loaded = load_region_series_entry(level, regionId)
    except IrrigationRuntimeDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Irrigation runtime statistics are unavailable",
        ) from exc
    if loaded is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Irrigation {level} region '{regionId}' was not found "
                "in precomputed irrigation statistics"
            ),
        )
    unit, region_data = loaded

    series = region_data.get(period)
    if not isinstance(series, list):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,

            detail=(
                f"Irrigation {period} series for {level} region "
                f"'{regionId}' was not found in precomputed irrigation statistics"
            ),
        )

    region = _find_region(regionId, level)
    if region is None:
        region = {
            "id": regionId,
            "name": str(region_data.get("name") or regionId),
            "level": level,
            "parentId": region_data.get("parentId"),
        }

    values = [float(entry["value"]) for entry in series]
    payload = {
        "region": region,
        "period": period,
        "unit": unit,
        "series": series,
        "summary": {
            "total": round(sum(values), 1),
            "average": round(sum(values) / len(values), 1) if values else 0,
            "max": max(values) if values else 0,
            "min": min(values) if values else 0,
        },
    }
    return _cached_json_response(request, payload)
