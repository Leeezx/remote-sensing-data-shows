"""Tests for metadata-driven raster colorization."""

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from backend.raster_rendering import colorize, render_png, valid_data_mask


SSM_LEGEND = [
    {"value": 0.09, "color": "#d53e4f"},
    {"value": 0.15, "color": "#fc8d59"},
    {"value": 0.22, "color": "#fee08b"},
    {"value": 0.28, "color": "#99d594"},
    {"value": 0.35, "color": "#3288bd"},
    {"value": 0.40, "color": "#016c59"},
]


def test_colorize_uses_exact_ssm_legend_stop_colors():
    values = np.array([[stop["value"] for stop in SSM_LEGEND]])

    rgba = colorize(values, SSM_LEGEND)

    expected_rgb = np.array(
        [[[213, 62, 79], [252, 141, 89], [254, 224, 139],
          [153, 213, 148], [50, 136, 189], [1, 108, 89]]],
        dtype=np.uint8,
    )
    np.testing.assert_array_equal(rgba[..., :3], expected_rgb)
    np.testing.assert_array_equal(rgba[..., 3], 255)


def test_colorize_interpolates_and_clamps_to_end_stops():
    legend = [
        {"value": 10, "color": "#000000"},
        {"value": 0, "color": "#ffffff"},
    ]
    values = np.array([[-1.0, 5.0, 11.0]])

    rgba = colorize(values, legend)

    np.testing.assert_array_equal(
        rgba,
        np.array([[[255, 255, 255, 255], [128, 128, 128, 255], [0, 0, 0, 255]]], dtype=np.uint8),
    )


def test_valid_data_mask_rejects_sentinels_nodata_and_source_mask_zeros():
    values = np.array([[1.0, np.nan, -999.0], [-32768.0, 2.0, 3.0]])
    source_mask = np.array([[1, 1, 1], [1, 0, 1]], dtype=np.uint8)

    mask = valid_data_mask(values, source_mask=source_mask, nodata=-32768.0)

    np.testing.assert_array_equal(
        mask,
        np.array([[True, False, False], [False, False, True]]),
    )


def test_colorize_makes_invalid_pixels_transparent():
    values = np.array([[0.0, np.nan, -999.0, -32768.0, 1.0]])
    source_mask = np.array([[1, 1, 1, 1, 0]], dtype=np.uint8)
    legend = [{"value": 0, "color": "#000000"}, {"value": 1, "color": "#ffffff"}]

    rgba = colorize(values, legend, source_mask=source_mask, nodata=-32768.0)

    np.testing.assert_array_equal(rgba[..., 3], np.array([[255, 0, 0, 0, 0]], dtype=np.uint8))


@pytest.mark.parametrize(
    ("values", "legend", "message"),
    [
        (np.zeros((1, 1, 1)), SSM_LEGEND, "2D"),
        (np.zeros((1, 1)), [{"value": 0, "color": "red"}], "#rrggbb"),
    ],
)
def test_colorize_rejects_malformed_dimensions_and_colors(values, legend, message):
    with pytest.raises(ValueError, match=message):
        colorize(values, legend)


def test_colorize_rejects_empty_legend_iterator():
    with pytest.raises(ValueError, match="at least one stop"):
        colorize(np.zeros((1, 1)), iter(()))


def test_colorize_rejects_non_finite_legend_values():
    legend = [{"value": np.inf, "color": "#000000"}]

    with pytest.raises(ValueError, match="finite numbers"):
        colorize(np.zeros((1, 1)), legend)


def test_colorize_rejects_duplicate_legend_values():
    legend = [
        {"value": 0, "color": "#000000"},
        {"value": 0.0, "color": "#ffffff"},
    ]

    with pytest.raises(ValueError, match="duplicate"):
        colorize(np.zeros((1, 1)), legend)


def test_render_png_encodes_rgba_bytes():
    rgba = np.array([[[1, 2, 3, 255], [4, 5, 6, 0]]], dtype=np.uint8)

    png = render_png(rgba)

    with Image.open(BytesIO(png)) as image:
        assert image.mode == "RGBA"
        assert image.size == (2, 1)
        np.testing.assert_array_equal(image, rgba)


def test_render_png_rejects_non_uint8_data():
    rgba = np.zeros((1, 1, 4), dtype=np.uint16)

    with pytest.raises(ValueError, match="uint8"):
        render_png(rgba)
