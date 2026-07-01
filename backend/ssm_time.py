"""Strict conversion of public SSM time identifiers to raster paths."""

from datetime import date
from pathlib import Path
import re


_PERIOD_ID = re.compile(r"^(?P<year>[0-9]{4})_(?P<period>[0-9]{2,3})$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_MONTH = re.compile(r"^[0-9]{4}-[0-9]{2}$")


def ssm_time_to_cog_name(time: str) -> str:
    """Return the SSM COG basename for one supported public time format."""
    period_match = _PERIOD_ID.fullmatch(time)
    if period_match:
        return f"{period_match.group('year')}_{period_match.group('period')}_cog.tif"

    try:
        if _DAY.fullmatch(time):
            selected = date.fromisoformat(time)
        elif _MONTH.fullmatch(time):
            year, month = (int(part) for part in time.split("-"))
            selected = date(year, month, 15)
        else:
            raise ValueError
    except ValueError as exc:
        raise ValueError(f"Invalid SSM time '{time}'") from exc

    start = date(selected.year, 1, 1)
    period = (selected - start).days // 8 + 1
    return f"{selected.year}_{period:02d}_cog.tif"


def ssm_time_to_cog_path(root: Path, time: str) -> Path:
    """Resolve a validated SSM time beneath ``root``."""
    cog_name = ssm_time_to_cog_name(time)
    if Path(cog_name).name != cog_name:
        raise ValueError(f"Invalid SSM time '{time}'")

    resolved_root = root.resolve()
    cog_path = (resolved_root / cog_name).resolve()
    try:
        cog_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Invalid SSM time '{time}'") from exc
    return cog_path
