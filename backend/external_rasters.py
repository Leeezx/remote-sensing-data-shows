"""Discovery and time-to-raster resolution for externally stored rasters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import re

import rasterio
from rasterio.errors import RasterioIOError

from backend.raster_rendering import valid_data_mask
from backend.runtime_config import RASTER_ROOT


@dataclass(frozen=True)
class ExternalRasterSpec:
    """Describe one externally stored raster layer."""

    root: Path
    layout: str  # ``annual_bands`` or ``period_files``
    value_scale: float = 1.0
    nodata_values: tuple[float, ...] = ()


@dataclass(frozen=True)
class RasterSource:
    """Resolved raster file and 1-based band for one public time value."""

    path: Path
    band: int


def _external_spec(
    cog_directory: str,
    layout: str,
    value_scale: float = 1.0,
    nodata_values: tuple[float, ...] = (),
) -> ExternalRasterSpec:
    """Describe a deployable project-local COG data source."""
    return ExternalRasterSpec(
        root=RASTER_ROOT / cog_directory,
        layout=layout,
        value_scale=value_scale,
        nodata_values=nodata_values,
    )


EXTERNAL_RASTERS: dict[str, ExternalRasterSpec] = {
    "et": _external_spec("et", "period_files", 0.1, (0,)),
    "sm_10cm": _external_spec("sm_10cm", "period_files", 0.001),
    "sm_30cm": _external_spec("sm_30cm", "period_files"),
    "sm_60cm": _external_spec("sm_60cm", "period_files"),
    "sm_100cm": _external_spec("sm_100cm", "period_files"),
}

_PERIOD_FILE = re.compile(
    r"(?P<year>20\d{2})[_-](?:8day[_-])?(?P<period>\d{1,3})(?:[_-].*)?$",
    re.IGNORECASE,
)
_ET_PERIOD_FILE = re.compile(
    r"(?P<year>20\d{2})_8day_(?P<period>0[1-9]|[1-3]\d|4[0-6])_cog\.tif$"
)
_DATE_TIME = re.compile(r"^(?P<year>20\d{2})-(?P<month>\d{2})-(?P<day>\d{2})$")
_PERIOD_TIME = re.compile(r"^(?P<year>20\d{2})_(?P<period>\d{1,3})$")
_SUPPORTED_EXTENSIONS = {".tif", ".tiff"}


def _period_date(year: int, period: int) -> date:
    if period < 1 or period > 60:
        raise ValueError(f"Invalid 8-day period '{year}_{period}'")
    return date(year, 1, 1) + timedelta(days=(period - 1) * 8)


def _time_to_period(time: str) -> tuple[int, int]:
    """Convert an ISO 8-day date or ``YYYY_PP`` identifier to a period."""
    period_match = _PERIOD_TIME.fullmatch(time)
    if period_match:
        year = int(period_match.group("year"))
        period = int(period_match.group("period"))
        _period_date(year, period)
        return year, period

    date_match = _DATE_TIME.fullmatch(time)
    if not date_match:
        raise ValueError(f"Invalid 8-day time '{time}'")
    try:
        selected = date(
            int(date_match.group("year")),
            int(date_match.group("month")),
            int(date_match.group("day")),
        )
    except ValueError as exc:
        raise ValueError(f"Invalid 8-day time '{time}'") from exc
    offset = (selected - date(selected.year, 1, 1)).days
    if offset % 8 != 0:
        raise ValueError(f"Time '{time}' is not the start of an 8-day period")
    return selected.year, offset // 8 + 1


def _iter_rasters(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in _SUPPORTED_EXTENSIONS
    )


def _candidate_roots(spec: ExternalRasterSpec) -> list[Path]:
    return [spec.root]


def _period_files(spec: ExternalRasterSpec) -> dict[tuple[int, int], Path]:
    files: dict[tuple[int, int], Path] = {}
    for key, paths in _period_file_candidates(spec).items():
        files[key] = paths[0]
    return files


def _period_file_candidates(
    spec: ExternalRasterSpec,
) -> dict[tuple[int, int], list[Path]]:
    files: dict[tuple[int, int], list[Path]] = {}
    for root in _candidate_roots(spec):
        for path in _iter_rasters(root):
            match = _PERIOD_FILE.search(path.stem)
            if not match:
                continue
            key = (int(match.group("year")), int(match.group("period")))
            files.setdefault(key, []).append(path)
    return files


def discover_period_sources(
    root: Path, *, reject_duplicates: bool = False
) -> dict[str, RasterSource]:
    """Map ISO dates to period-file band-1 sources under an explicit root."""
    spec = ExternalRasterSpec(root, "period_files")
    candidates = _period_file_candidates(spec)
    if reject_duplicates:
        duplicates = {
            _period_date(year, period).isoformat(): paths
            for (year, period), paths in candidates.items()
            if len(paths) != 1
        }
        if duplicates:
            dates = ", ".join(sorted(duplicates))
            raise ValueError(f"Duplicate raster files for ET time(s): {dates}")
    canonical_candidates = {
        key: [path for path in paths if _ET_PERIOD_FILE.fullmatch(path.name)]
        for key, paths in candidates.items()
    }
    return {
        _period_date(year, period).isoformat(): RasterSource(
            path=paths[0].resolve(),
            band=1,
        )
        for (year, period), paths in sorted(canonical_candidates.items())
        if paths
    }


def _annual_files(spec: ExternalRasterSpec) -> dict[int, Path]:
    files: dict[int, Path] = {}
    for root in _candidate_roots(spec):
        for path in _iter_rasters(root):
            years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", path.stem)
            if len(years) != 1:
                continue
            files.setdefault(int(years[0]), path)
    return files


def discover_external_times(layer_id: str) -> list[str]:
    """Return available ISO 8-day dates discovered from one external layer."""
    spec = EXTERNAL_RASTERS.get(layer_id)
    if spec is None:
        raise KeyError(f"Unknown external layer '{layer_id}'")

    periods: set[tuple[int, int]] = set()
    if spec.layout == "period_files":
        if layer_id == "et":
            return list(discover_period_sources(spec.root))
        periods.update(_period_files(spec))
    else:
        for year, path in _annual_files(spec).items():
            try:
                with rasterio.open(path) as source:
                    periods.update((year, period) for period in range(1, source.count + 1))
            except RasterioIOError:
                continue

    return [_period_date(year, period).isoformat() for year, period in sorted(periods)]


def resolve_external_raster(layer_id: str, time: str) -> RasterSource:
    """Resolve a layer/time pair to a safe file path and band number."""
    spec = EXTERNAL_RASTERS.get(layer_id)
    if spec is None:
        raise ValueError(f"Unknown external layer '{layer_id}'")
    year, period = _time_to_period(time)

    if spec.layout == "period_files":
        if layer_id == "et":
            source = discover_period_sources(spec.root).get(
                _period_date(year, period).isoformat()
            )
            if source is None:
                raise FileNotFoundError(
                    f"No raster found for layer '{layer_id}' at time '{time}'"
                )
            return source
        paths = _period_file_candidates(spec).get((year, period))
        if not paths:
            raise FileNotFoundError(
                f"No raster found for layer '{layer_id}' at time '{time}'"
            )
        path = paths[0]
        return RasterSource(path=path.resolve(), band=1)

    path = _annual_files(spec).get(year)
    if path is None:
        raise FileNotFoundError(
            f"No annual raster found for layer '{layer_id}' in {year}"
        )
    try:
        with rasterio.open(path) as source:
            if period > source.count:
                raise FileNotFoundError(
                    f"Raster for layer '{layer_id}' has no band for time '{time}'"
                )
    except RasterioIOError as exc:
        raise FileNotFoundError(f"Unable to read raster '{path.name}'") from exc
    return RasterSource(path=path.resolve(), band=period)


def external_value_scale(layer_id: str) -> float:
    """Return the storage-to-display multiplier for one external layer."""
    spec = EXTERNAL_RASTERS.get(layer_id)
    if spec is None:
        raise KeyError(f"Unknown external layer '{layer_id}'")
    return spec.value_scale


def external_valid_data_mask(layer_id: str, values, source_mask=None, nodata=None):
    """Apply source masks plus layer-specific NoData conventions."""
    mask = valid_data_mask(values, source_mask=source_mask, nodata=nodata)
    for value in EXTERNAL_RASTERS[layer_id].nodata_values:
        mask &= values != value
    return mask
