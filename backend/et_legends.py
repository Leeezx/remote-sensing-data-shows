"""Construction and persisted loading for ET legends."""

from datetime import date
from functools import lru_cache
import json
import math
from numbers import Real
from pathlib import Path
import threading

import numpy as np

from backend.raster_rendering import valid_data_mask


ET_LEGEND_CACHE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "et_legends.json"
)
_CACHE_LOCK = threading.Lock()


class ETLegendUnavailableError(RuntimeError):
    """The persisted ET legend document cannot serve the requested time."""


def _copy_legend(legend):
    return [dict(item) for item in legend]


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
        raise ETLegendUnavailableError("Unsupported ET legend version")

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
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ETLegendUnavailableError(
            "Unable to load ET legend document"
        ) from None
    return validate_et_legend_document(document)


def get_precomputed_et_legend(
    time: str,
    path: Path | None = None,
) -> list[dict]:
    """Return a cached persisted ET legend as fresh mutable dictionaries."""
    selected_path = ET_LEGEND_CACHE_PATH if path is None else path
    try:
        resolved_path = Path(selected_path).resolve()
        stat = resolved_path.stat()
    except OSError:
        raise ETLegendUnavailableError(
            "Unable to access ET legend document"
        ) from None

    with _CACHE_LOCK:
        legends = _load_et_legend_document(
            str(resolved_path),
            stat.st_mtime_ns,
            stat.st_size,
        )

    try:
        legend = legends[time]
    except (KeyError, TypeError):
        raise ETLegendUnavailableError(
            f"No precomputed ET legend for time '{time}'"
        ) from None

    return [
        {"value": value, "color": color, "label": label}
        for value, color, label in legend
    ]
