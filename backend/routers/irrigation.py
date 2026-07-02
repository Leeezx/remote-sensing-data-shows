"""Irrigation water router — raster metadata and administrative statistics."""

from typing import Literal
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

from backend.data_loader import (
    IRRIGATION_8DAY_ROOT,
    IRRIGATION_ANNUAL_ROOT,
    IRRIGATION_ANNUAL_COG_ROOT,
    IRRIGATION_8DAY_COG_ROOT,
    get_irrigation_layer,
    get_irrigation_region_series,
    get_irrigation_regions,
    get_irrigation_times,
)
from backend.irrigation_stats import compute_irrigation_region_series
from backend.irrigation_time import irrigation_time_to_cog_path, irrigation_time_to_path
from backend.irrigation_legend import get_irrigation_dynamic_legend
from backend.shapefile_geojson import read_shapefile_geojson

router = APIRouter(tags=["irrigation"])

RegionLevel = Literal["county", "village"]
SeriesPeriod = Literal["annual", "monthly"]
RasterResolution = Literal["annual", "month"]
COUNTY_VECTOR_PATH = Path(r"F:\矢量底图\中国_县\中国_县.shp")
VILLAGE_VECTOR_PATH: Path | None = None


def _find_region(region_id: str, level: RegionLevel) -> dict | None:
    for region in get_irrigation_regions():
        if region["id"] == region_id and region["level"] == level:
            return region
    return None


def find_irrigation_vector_feature(level: RegionLevel, region_id: str) -> dict | None:
    """Find an administrative vector feature by id."""
    path = COUNTY_VECTOR_PATH if level == "county" else VILLAGE_VECTOR_PATH
    if not path or not path.is_file():
        return None
    data = read_shapefile_geojson(path)
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        feature_id = str(
            properties.get("id")
            or properties.get("gb")
            or properties.get("GB")
            or properties.get("name")
            or ""
        )
        if feature_id == region_id:
            return feature
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    return {
        "level": level,
        "available": bool(VILLAGE_VECTOR_PATH and VILLAGE_VECTOR_PATH.is_file()),
        "url": "/api/irrigation/vectors/village"
        if VILLAGE_VECTOR_PATH and VILLAGE_VECTOR_PATH.is_file()
        else None,
        "message": "村级行政区矢量暂未配置",
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


@router.get("/irrigation/vectors/village")
def village_vector_geojson():
    """Return village administrative boundaries as GeoJSON when configured."""
    if not VILLAGE_VECTOR_PATH or not VILLAGE_VECTOR_PATH.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Village vector file is not configured",
        )
    return read_shapefile_geojson(VILLAGE_VECTOR_PATH)


@router.get("/irrigation/regions")
def irrigation_regions(level: RegionLevel | None = Query(default=None)):
    """Return county and village administrative units for irrigation statistics."""
    regions = get_irrigation_regions()
    if level is None:
        return regions
    return [region for region in regions if region["level"] == level]


@router.get("/irrigation/series")
def irrigation_series(
    level: RegionLevel = Query(...),
    regionId: str = Query(...),
    period: SeriesPeriod = Query(default="annual"),
):
    """Return precomputed irrigation water totals for one administrative region."""
    series_data = get_irrigation_region_series()
    region = _find_region(regionId, level)
    try:
        series = series_data[level][regionId][period]
    except KeyError as exc:
        feature = find_irrigation_vector_feature(level, regionId)
        if feature is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Irrigation {level} region '{regionId}' not found",
            ) from exc
        properties = feature.get("properties", {})
        region_name = str(properties.get("name") or properties.get("NAME") or regionId)
        region = {
            "id": regionId,
            "name": region_name,
            "level": level,
            "parentId": None,
        }
        try:
            series = compute_irrigation_region_series(
                level,
                regionId,
                region_name,
                feature["geometry"],
                period,
            )
        except ValueError as compute_error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(compute_error),
            ) from compute_error

    if region is None:
        region = {
            "id": regionId,
            "name": regionId,
            "level": level,
            "parentId": None,
        }

    values = [float(entry["value"]) for entry in series]
    return {
        "region": region,
        "period": period,
        "unit": series_data["unit"],
        "series": series,
        "summary": {
            "total": round(sum(values), 1),
            "average": round(sum(values) / len(values), 1) if values else 0,
            "max": max(values) if values else 0,
            "min": min(values) if values else 0,
        },
    }
