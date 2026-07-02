"""Resolve public irrigation water time identifiers to raster files."""

from datetime import date
from pathlib import Path
import re


_YEAR = re.compile(r"^[0-9]{4}$")
_MONTH = re.compile(r"^[0-9]{4}-[0-9]{2}$")
_PERIOD_ID = re.compile(r"^(?P<year>[0-9]{4})_(?P<period>[0-9]{1,3})$")


def irrigation_time_to_name(time: str) -> str:
    """Return the irrigation raster basename for a public time value."""
    if _YEAR.fullmatch(time):
        return f"IWU_{time}.TIF"

    period_match = _PERIOD_ID.fullmatch(time)
    if period_match:
        return f"IWU_{period_match.group('year')}_{period_match.group('period')}.tif"

    try:
        if _MONTH.fullmatch(time):
            year, month = (int(part) for part in time.split("-"))
            selected = date(year, month, 15)
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"Invalid irrigation time '{time}'") from exc

    start = date(selected.year, 1, 1)
    period = (selected - start).days // 8 + 1
    return f"IWU_{selected.year}_{period:02d}.tif"


def _resolve_safe(root: Path, raster_name: str, time: str) -> Path:
    """Resolve and validate a raster path under *root*."""
    resolved_root = root.resolve()
    raster_path = (resolved_root / raster_name).resolve()
    try:
        raster_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Invalid irrigation time '{time}'") from exc
    return raster_path


def irrigation_time_to_path(
    annual_root: Path,
    eight_day_root: Path,
    time: str,
) -> Path:
    """Resolve a validated irrigation public time under the configured roots."""
    raster_name = irrigation_time_to_name(time)
    if Path(raster_name).name != raster_name:
        raise ValueError(f"Invalid irrigation time '{time}'")
    root = annual_root if _YEAR.fullmatch(time) else eight_day_root
    return _resolve_safe(root, raster_name, time)


def irrigation_time_to_cog_path(
    annual_root: Path,
    annual_cog_root: Path,
    eight_day_root: Path,
    eight_day_cog_root: Path,
    time: str,
) -> Path:
    """Resolve to a COG raster path when available, falling back to original.

    Returns the COG path when the file exists; otherwise returns the
    original (non-COG) path so the application works before and after
    conversion without configuration changes.
    """
    raster_name = irrigation_time_to_name(time)
    if Path(raster_name).name != raster_name:
        raise ValueError(f"Invalid irrigation time '{time}'")
    if _YEAR.fullmatch(time):
        cog_path = _resolve_safe(annual_cog_root, raster_name, time)
        if cog_path.is_file():
            return cog_path
        return _resolve_safe(annual_root, raster_name, time)
    cog_path = _resolve_safe(eight_day_cog_root, raster_name, time)
    if cog_path.is_file():
        return cog_path
    return _resolve_safe(eight_day_root, raster_name, time)
