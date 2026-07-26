"""Helpers for serving checked-in reclamation map artifacts."""

import json
from pathlib import Path


SCHEMA_VERSION = 1


def _accepts_gzip(accept_encoding: str) -> bool:
    """Return whether the request permits a gzip representation."""
    for entry in accept_encoding.split(","):
        parts = [part.strip() for part in entry.split(";")]
        if not parts or parts[0].lower() != "gzip":
            continue
        quality = 1.0
        for parameter in parts[1:]:
            name, separator, value = parameter.partition("=")
            if name.strip().lower() != "q" or not separator:
                continue
            try:
                quality = float(value.strip())
            except ValueError:
                quality = 0.0
        if 0 < quality <= 1:
            return True
    return False


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
    if _accepts_gzip(accept_encoding) and gzip_path.is_file():
        headers["Content-Encoding"] = "gzip"
        return gzip_path, headers
    return raw, headers
