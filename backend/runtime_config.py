"""Validated runtime configuration shared across backend modules."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def path_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


def positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def parse_cors_origins(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return raw == "true"


RASTER_ROOT = path_env("RASTER_ROOT", PROJECT_ROOT / "data" / "rasters")
IRRIGATION_ANNUAL_ROOT = path_env(
    "IRRIGATION_ANNUAL_ROOT", RASTER_ROOT / "irrigation_annual"
)
IRRIGATION_8DAY_ROOT = path_env(
    "IRRIGATION_8DAY_ROOT", RASTER_ROOT / "irrigation_8day"
)
IRRIGATION_ANNUAL_COG_ROOT = path_env(
    "IRRIGATION_ANNUAL_COG_ROOT", RASTER_ROOT / "irrigation_annual"
)
IRRIGATION_8DAY_COG_ROOT = path_env(
    "IRRIGATION_8DAY_COG_ROOT", RASTER_ROOT / "irrigation_8day"
)
IRRIGATION_REGION_SERIES_PATH = path_env(
    "IRRIGATION_REGION_SERIES_PATH",
    PROJECT_ROOT / "data" / "stats" / "irrigation_region_series.json",
)
CACHE_ROOT = path_env("CACHE_ROOT", PROJECT_ROOT / ".runtime-cache")
COUNTY_VECTOR_PATH = path_env(
    "COUNTY_VECTOR_PATH",
    PROJECT_ROOT
    / "data"
    / "vectors"
    / "irrigation"
    / "county"
    / "china_county.shp",
)
TOWNSHIP_CHUNK_ROOT = path_env(
    "TOWNSHIP_CHUNK_ROOT",
    PROJECT_ROOT / "data" / "vectors" / "irrigation" / "township_by_county",
)
MAX_AREA_QUERY_PIXELS = positive_int_env("MAX_AREA_QUERY_PIXELS", 4_000_000)
ENABLE_API_DOCS = bool_env("ENABLE_API_DOCS", False)
CORS_ORIGINS = parse_cors_origins(
    os.getenv("CORS_ORIGINS", "http://localhost:5173")
)
