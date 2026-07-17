"""Helpers for serving precomputed county-scoped township GeoJSON chunks."""

from __future__ import annotations

import json
from pathlib import Path


COUNTY_SOURCE_PREFIX = "156"
MAX_TOWNSHIP_FEATURES = 499
MAX_TOWNSHIP_CHUNK_BYTES = 1_000_000


def county_code_from_id(county_id: str) -> str:
    """Return a six-digit GB county code from the county vector identifier."""
    value = str(county_id).strip()
    if len(value) == 9 and value.startswith(COUNTY_SOURCE_PREFIX):
        value = value[-6:]
    if len(value) != 6 or not value.isdigit():
        raise ValueError("countyId must be a six-digit code or a 156-prefixed county id")
    return value


def county_id_from_code(county_code: str) -> str:
    return f"{COUNTY_SOURCE_PREFIX}{county_code_from_id(county_code)}"


def township_parent_code(township_id: str) -> str:
    value = str(township_id).strip()
    if len(value) != 12 or not value.isdigit():
        raise ValueError("township id must be a twelve-digit administrative code")
    return value[:6]


def township_chunk_path(root: Path, county_id: str) -> Path:
    return root / f"{county_code_from_id(county_id)}.geojson"


def load_township_chunk(root: Path, county_id: str) -> dict:
    path = township_chunk_path(root, county_id)
    return json.loads(path.read_text(encoding="utf-8"))
