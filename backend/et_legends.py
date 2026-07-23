"""Construction and persisted loading for ET legends."""

from datetime import date
from functools import lru_cache
import json
import logging
import math
from numbers import Real
from pathlib import Path
import threading

import numpy as np

from backend.raster_rendering import valid_data_mask


ET_LEGEND_CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "stats" / "et_legends.json"
)
_CACHE_LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)
ET_LEGEND_COLORS = (
    "#d53e4f",
    "#fc8d59",
    "#fee08b",
    "#99d594",
    "#3288bd",
    "#016c59",
)


class ETLegendUnavailableError(RuntimeError):
    """The persisted ET legend document cannot serve the requested time."""

    def __init__(self, message: str, *, category: str = "invalid-document"):
        super().__init__(message)
        self.category = category


def _copy_legend(legend):
    return [dict(item) for item in legend]


def _with_fixed_palette(legend):
    return [
        {**dict(item), "color": color}
        for item, color in zip(legend, ET_LEGEND_COLORS)
    ]


def build_et_legend(
    values,
    base_legend,
    unit,
    *,
    source_mask=None,
    nodata=None,
    value_scale=0.1,
    nodata_values=(0,),
) -> list[dict]:
    """Build six percentile stops from valid raw ET pixels."""
    base_legend = list(base_legend)
    if len(base_legend) != 6:
        return _copy_legend(base_legend)
    base_legend = _with_fixed_palette(base_legend)

    raw_values = np.asarray(values)
    valid = valid_data_mask(
        raw_values,
        source_mask=source_mask,
        nodata=nodata,
    )
    if nodata_values is not None:
        valid &= ~np.isin(raw_values, tuple(nodata_values))

    valid_values = raw_values[valid].astype(float, copy=False) * value_scale
    valid_values = valid_values[
        np.isfinite(valid_values) & (valid_values > 0)
    ]
    if valid_values.size < 6:
        return _copy_legend(base_legend)

    stops = np.percentile(valid_values, np.linspace(2, 98, 6))
    if not np.all(np.isfinite(stops)) or not np.all(np.diff(stops) > 0):
        return _copy_legend(base_legend)

    return [
        {
            "value": float(value),
            "color": item["color"],
            "label": f"{value:.1f} {unit}".strip(),
        }
        for value, item in zip(stops, base_legend)
    ]


def validate_et_legend_document(
    document,
) -> dict[str, tuple[tuple[float, str, str], ...]]:
    """Validate and normalize a version-one persisted ET legend document."""
    if not isinstance(document, dict):
        raise ETLegendUnavailableError("ET legend document must be an object")
    if (
        isinstance(document.get("version"), bool)
        or document.get("version") != 1
    ):
        raise ETLegendUnavailableError(
            "Unsupported ET legend version",
            category="unsupported-version",
        )

    legends = document.get("legends")
    if not isinstance(legends, dict):
        raise ETLegendUnavailableError("ET legend legends must be an object")

    validated = {}
    for time, items in legends.items():
        try:
            parsed_time = date.fromisoformat(time)
        except (TypeError, ValueError):
            raise ETLegendUnavailableError(
                "ET legend date key must be an ISO date"
            ) from None
        if parsed_time.isoformat() != time:
            raise ETLegendUnavailableError(
                "ET legend date key must be an ISO date"
            )
        if not isinstance(items, list) or len(items) != 6:
            raise ETLegendUnavailableError(
                f"ET legend for '{time}' must contain exactly 6 items"
            )

        normalized_items = []
        previous_value = None
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ETLegendUnavailableError(
                    f"ET legend item {index} must be an object"
                )

            value = item.get("value")
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ETLegendUnavailableError(
                    f"ET legend item {index} value must be a finite number"
                )
            try:
                normalized_value = float(value)
            except (OverflowError, TypeError, ValueError):
                raise ETLegendUnavailableError(
                    f"ET legend item {index} value must be a finite number"
                ) from None
            if not math.isfinite(normalized_value):
                raise ETLegendUnavailableError(
                    f"ET legend item {index} value must be a finite number"
                )

            color = item.get("color")
            if not isinstance(color, str):
                raise ETLegendUnavailableError(
                    f"ET legend item {index} color must be a string"
                )
            if color != ET_LEGEND_COLORS[index - 1]:
                raise ETLegendUnavailableError(
                    "ET legend colors must match the canonical ET palette",
                    category="invalid-palette",
                )
            label = item.get("label")
            if not isinstance(label, str):
                raise ETLegendUnavailableError(
                    f"ET legend item {index} label must be a string"
                )
            if previous_value is not None and normalized_value <= previous_value:
                raise ETLegendUnavailableError(
                    f"ET legend values must be strictly increasing for '{time}'"
                )

            normalized_items.append((normalized_value, color, label))
            previous_value = normalized_value

        validated[time] = tuple(normalized_items)

    return validated


@lru_cache(maxsize=4)
def _load_et_legend_document(
    resolved_path: str,
    mtime_ns: int,
    size: int,
) -> dict[str, tuple[tuple[float, str, str], ...]]:
    del mtime_ns, size
    try:
        serialized = Path(resolved_path).read_text(encoding="utf-8")
        document = json.loads(serialized)
    except FileNotFoundError:
        raise ETLegendUnavailableError(
            "Unable to load ET legend document",
            category="missing-file",
        ) from None
    except OSError:
        raise ETLegendUnavailableError(
            "Unable to load ET legend document",
            category="read-error",
        ) from None
    except (UnicodeError, json.JSONDecodeError):
        raise ETLegendUnavailableError(
            "Unable to load ET legend document",
            category="invalid-json",
        ) from None
    return validate_et_legend_document(document)


@lru_cache(maxsize=128)
def _log_legend_failure(category: str, basename: str, time: str) -> None:
    LOGGER.error(
        "ET legend unavailable category=%s file=%s time=%s",
        category,
        basename,
        time,
    )


def get_precomputed_et_legend(
    time: str,
    path: Path | None = None,
) -> list[dict]:
    """Return a cached persisted ET legend as fresh mutable dictionaries."""
    selected_path = ET_LEGEND_CACHE_PATH if path is None else path
    basename = Path(selected_path).name
    try:
        resolved_path = Path(selected_path).resolve()
        stat = resolved_path.stat()
    except FileNotFoundError:
        _log_legend_failure("missing-file", basename, time)
        raise ETLegendUnavailableError(
            "Unable to access ET legend document",
            category="missing-file",
        ) from None
    except OSError:
        _log_legend_failure("access-error", basename, time)
        raise ETLegendUnavailableError(
            "Unable to access ET legend document",
            category="access-error",
        ) from None

    try:
        with _CACHE_LOCK:
            legends = _load_et_legend_document(
                str(resolved_path),
                stat.st_mtime_ns,
                stat.st_size,
            )
    except ETLegendUnavailableError as exc:
        _log_legend_failure(exc.category, basename, time)
        raise

    try:
        legend = legends[time]
    except (KeyError, TypeError):
        _log_legend_failure("missing-time", basename, time)
        raise ETLegendUnavailableError(
            f"No precomputed ET legend for time '{time}'",
            category="missing-time",
        ) from None

    return [
        {"value": value, "color": color, "label": label}
        for value, color, label in legend
    ]
