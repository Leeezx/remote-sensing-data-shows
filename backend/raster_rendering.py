"""Utilities for coloring single-band rasters from layer legend metadata."""

import re

import numpy as np
from rio_tiler.utils import render


HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def valid_data_mask(values, source_mask=None, nodata=None):
    """Return pixels that contain finite, unmasked, non-sentinel data."""
    values = np.asarray(values)
    mask = np.isfinite(values) & (values != -999)

    if nodata is not None and np.isfinite(nodata):
        mask &= values != nodata

    if source_mask is not None:
        source_mask = np.asarray(source_mask)
        if source_mask.shape != values.shape:
            raise ValueError("source_mask dimensions must match values")
        mask &= source_mask.astype(bool)

    return mask


def colorize(values, legend, source_mask=None, nodata=None, nodata_color=None):
    """Colorize one 2D raster band using numeric legend stops."""
    values = np.asarray(values)
    if values.ndim != 2:
        raise ValueError("values must be a 2D raster band")
    try:
        legend = list(legend)
    except TypeError as exc:
        raise ValueError("legend must be an iterable of stops") from exc
    if not legend:
        raise ValueError("legend must contain at least one stop")

    stops = []
    for item in legend:
        color = item.get("color") if isinstance(item, dict) else None
        value = item.get("value") if isinstance(item, dict) else None
        if not isinstance(color, str) or not HEX_COLOR.fullmatch(color):
            raise ValueError("legend colors must use #rrggbb format")
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not np.isfinite(value):
            raise ValueError("legend values must be finite numbers")
        stops.append((float(value), tuple(bytes.fromhex(color[1:]))))

    stops.sort(key=lambda stop: stop[0])
    if any(current[0] == previous[0] for previous, current in zip(stops, stops[1:])):
        raise ValueError("legend must not contain duplicate values")
    stop_values = np.array([stop[0] for stop in stops])
    stop_colors = np.array([stop[1] for stop in stops])
    valid = valid_data_mask(values, source_mask=source_mask, nodata=nodata)
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if nodata_color is not None:
        rgba[..., :] = nodata_color

    for channel in range(3):
        interpolated = np.interp(
            values[valid],
            stop_values,
            stop_colors[:, channel],
            left=stop_colors[0, channel],
            right=stop_colors[-1, channel],
        )
        rgba[..., channel][valid] = np.rint(interpolated).astype(np.uint8)
    rgba[..., 3][valid] = 255
    return rgba


def render_png(rgba):
    """Encode an HxWx4 RGBA array as PNG bytes."""
    rgba = np.asarray(rgba)
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("rgba must have dimensions HxWx4")
    if rgba.dtype != np.uint8:
        raise ValueError("rgba must use uint8 data")
    return render(np.moveaxis(rgba, -1, 0), img_format="PNG")
