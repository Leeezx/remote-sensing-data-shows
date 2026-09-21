"""Helpers for serving checked-in water-demand map artifacts."""

import json
from pathlib import Path


SCHEMA_VERSION = 1
POINTS_MEDIA_TYPE = "application/octet-stream"


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
    """Load and validate the water-demand artifact manifest."""
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Unsupported water-demand schema version")
    return data


def choose_representation(
    root: Path,
    relative_name: str,
    accept_encoding: str,
) -> tuple[Path, dict[str, str]]:
    """Choose a safe raw or gzip representation for a client request."""
    raw = (root / relative_name).resolve()
    if root.resolve() not in raw.parents or not raw.is_file():
        raise FileNotFoundError(relative_name)
    gzip_path = raw.with_suffix(raw.suffix + ".gz")
    headers = {"Vary": "Accept-Encoding"}
    if _accepts_gzip(accept_encoding) and gzip_path.is_file():
        headers["Content-Encoding"] = "gzip"
        return gzip_path, headers
    return raw, headers
