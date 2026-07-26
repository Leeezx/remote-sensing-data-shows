"""Helpers for serving checked-in reclamation map artifacts."""

import json
from pathlib import Path


SCHEMA_VERSION = 1


def load_manifest(root: Path) -> dict:
    """Load and validate the reclamation artifact manifest."""
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Unsupported reclamation schema version")
    return data


def region_ids(root: Path) -> set[str]:
    """Return region identifiers declared by the artifact manifest."""
    return {str(region["id"]) for region in load_manifest(root)["regions"]}


def choose_representation(
    root: Path,
    relative_json: Path,
    accept_encoding: str,
) -> tuple[Path, dict[str, str]]:
    """Choose a safe raw or gzip JSON representation for a client request."""
    raw = (root / relative_json).resolve()
    if root.resolve() not in raw.parents or not raw.is_file():
        raise FileNotFoundError(relative_json)
    gzip_path = raw.with_suffix(raw.suffix + ".gz")
    headers = {"Vary": "Accept-Encoding"}
    if "gzip" in accept_encoding.lower() and gzip_path.is_file():
        headers["Content-Encoding"] = "gzip"
        return gzip_path, headers
    return raw, headers
