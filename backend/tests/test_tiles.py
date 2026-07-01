"""Tests for the tile serving endpoint."""

import inspect
from types import SimpleNamespace
import warnings

import numpy as np
import pytest

from fastapi.testclient import TestClient
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rio_tiler.errors import TileOutsideBounds

from backend.main import app
from backend.routers import tiles
from backend.ssm_time import ssm_time_to_cog_name

client = TestClient(app)


@pytest.mark.parametrize(
    ("time", "expected"),
    [
        ("2010_01", "2010_01_cog.tif"),
        ("2010_005", "2010_005_cog.tif"),
        ("2010-02-02", "2010_05_cog.tif"),
        ("2010-02", "2010_06_cog.tif"),
    ],
)
def test_ssm_time_to_cog_name_preserves_supported_mappings(time, expected):
    assert ssm_time_to_cog_name(time) == expected


@pytest.mark.parametrize(
    "time",
    [
        "",
        "../secret_01",
        ".._..",
        "2010_01/../../x",
        "2010-13",
        "2010-02-30",
        "foo_bar",
    ],
)
def test_ssm_time_to_cog_name_rejects_unsupported_values(time):
    with pytest.raises(ValueError, match="Invalid SSM time"):
        ssm_time_to_cog_name(time)


def test_ssm_tile_route_is_synchronous():
    assert not inspect.iscoroutinefunction(tiles.ssm_tile_proxy)


def test_tile_not_found():
    """GET /data/tiles/... returns 404 when tile does not exist."""
    response = client.get("/data/tiles/ndvi/2025-06/5/12/12.png")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_tile_invalid_layer():
    """GET /data/tiles/... with an invalid layer returns 404."""
    response = client.get("/data/tiles/unknown/2025-06/5/12/12.png")
    assert response.status_code == 404


def test_render_ssm_tile_reads_first_band_and_mask_from_cog(monkeypatch, tmp_path):
    values = np.array([[[0.09, 0.40, 0.25]]], dtype=np.float32)
    mask = np.array([[255, 255, 0]], dtype=np.uint8)
    calls = []
    legend_calls = []
    dynamic_legend = [
        {"value": 0.09, "color": "#010203", "label": "low"},
        {"value": 0.40, "color": "#a0b0c0", "label": "high"},
    ]

    class FakeCOGReader:
        def __init__(self, path):
            calls.append(("open", path))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def tile(self, x, y, z, indexes=None):
            calls.append(("tile", x, y, z, indexes))
            return SimpleNamespace(data=values, mask=mask)

    monkeypatch.setattr(tiles, "COGReader", FakeCOGReader)
    monkeypatch.setattr(
        tiles,
        "get_dynamic_legend",
        lambda *args: legend_calls.append(args) or dynamic_legend,
    )

    cog_path = tmp_path / "ssm.tif"
    png = tiles._render_ssm_tile(cog_path, x=3, y=4, z=5)

    assert calls == [("open", str(cog_path)), ("tile", 3, 4, 5, 1)]
    layer = tiles.get_layer("ssm")
    assert legend_calls == [(cog_path, layer["legend"], layer["unit"])]
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with MemoryFile(png) as memory_file:
            with memory_file.open() as dataset:
                decoded = np.moveaxis(dataset.read(), 0, -1)
    np.testing.assert_array_equal(
        decoded,
        np.array(
            [[[1, 2, 3, 255], [160, 176, 192, 255], [0, 0, 0, 0]]],
            dtype=np.uint8,
        ),
    )


def test_render_ssm_tile_reports_missing_layer(monkeypatch, tmp_path):
    monkeypatch.setattr(tiles, "get_layer", lambda _layer_id: None)

    with pytest.raises(RuntimeError, match="SSM layer metadata is missing"):
        tiles._render_ssm_tile(tmp_path / "ssm.tif", x=3, y=4, z=5)


@pytest.mark.parametrize("layer", [{}, {"legend": []}])
def test_render_ssm_tile_reports_missing_or_empty_legend(monkeypatch, tmp_path, layer):
    monkeypatch.setattr(tiles, "get_layer", lambda _layer_id: layer)

    with pytest.raises(RuntimeError, match="SSM layer legend is missing or empty"):
        tiles._render_ssm_tile(tmp_path / "ssm.tif", x=3, y=4, z=5)


def test_ssm_tile_route_renders_existing_cog_without_titiler_parameters(monkeypatch, tmp_path):
    cog_path = tmp_path / "data" / "rasters" / "ssm" / "2010_01_cog.tif"
    cog_path.parent.mkdir(parents=True)
    cog_path.touch()
    rendered = b"\x89PNG\r\n\x1a\nrendered"
    calls = []
    monkeypatch.setattr(tiles, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        tiles,
        "_render_ssm_tile",
        lambda path, x, y, z: calls.append((path, x, y, z)) or rendered,
    )

    response = client.get("/data/ssm-tiles/WebMercatorQuad/5/3/4.png?time=2010_01")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == rendered
    assert calls == [(cog_path, 3, 4, 5)]


@pytest.mark.parametrize("tile_matrix_set", ["WorldCRS84Quad", "unknown"])
def test_ssm_tile_route_rejects_unsupported_tile_matrix_set_without_rendering(
    monkeypatch, tmp_path, tile_matrix_set
):
    cog_path = tmp_path / "data" / "rasters" / "ssm" / "2010_01_cog.tif"
    cog_path.parent.mkdir(parents=True)
    cog_path.touch()
    calls = []
    monkeypatch.setattr(tiles, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        tiles,
        "_render_ssm_tile",
        lambda *_args: calls.append(_args),
    )

    response = client.get(
        f"/data/ssm-tiles/{tile_matrix_set}/5/3/4.png?time=2010_01"
    )

    assert 400 <= response.status_code < 500
    assert "WebMercatorQuad" in response.text
    assert calls == []


def test_ssm_tile_route_returns_transparent_png_outside_bounds(monkeypatch, tmp_path):
    cog_path = tmp_path / "data" / "rasters" / "ssm" / "2010_01_cog.tif"
    cog_path.parent.mkdir(parents=True)
    cog_path.touch()
    monkeypatch.setattr(tiles, "PROJECT_ROOT", tmp_path)

    def outside_bounds(*_args):
        raise TileOutsideBounds("outside raster bounds")

    monkeypatch.setattr(tiles, "_render_ssm_tile", outside_bounds)

    response = client.get("/data/ssm-tiles/WebMercatorQuad/5/3/4.png?time=2010_01")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == tiles.TRANSPARENT_PNG


def test_ssm_tile_route_reports_missing_cog(monkeypatch, tmp_path):
    monkeypatch.setattr(tiles, "PROJECT_ROOT", tmp_path)

    response = client.get("/data/ssm-tiles/WebMercatorQuad/5/3/4.png?time=2010_01")

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "COG file not found for time '2010_01' (looked for: 2010_01_cog.tif)"
    )


@pytest.mark.parametrize(
    "time",
    [
        "",
        "../secret_01",
        ".._..",
        "2010_01/../../x",
        "2010-13",
        "2010-02-30",
        "foo_bar",
    ],
)
def test_ssm_tile_route_rejects_invalid_time_without_rendering(
    monkeypatch, tmp_path, time
):
    calls = []
    monkeypatch.setattr(tiles, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        tiles, "_render_ssm_tile", lambda *_args: calls.append(_args)
    )

    response = client.get(
        "/data/ssm-tiles/WebMercatorQuad/5/3/4.png", params={"time": time}
    )

    assert response.status_code == 422
    assert "Invalid SSM time" in response.json()["detail"]
    assert calls == []
