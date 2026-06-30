"""Tests for the tile serving endpoint."""

from types import SimpleNamespace
import warnings

import numpy as np

from fastapi.testclient import TestClient
from rasterio.errors import NotGeoreferencedWarning
from rasterio.io import MemoryFile
from rio_tiler.errors import TileOutsideBounds

from backend.main import app
from backend.routers import tiles

client = TestClient(app)


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
    values = np.array([[[0.09, 0.40]]], dtype=np.float32)
    mask = np.array([[255, 0]], dtype=np.uint8)
    calls = []

    class FakeCOGReader:
        def __init__(self, path):
            calls.append(("open", path))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def tile(self, x, y, z):
            calls.append(("tile", x, y, z))
            return SimpleNamespace(data=values, mask=mask)

    monkeypatch.setattr(tiles, "COGReader", FakeCOGReader)

    cog_path = tmp_path / "ssm.tif"
    png = tiles._render_ssm_tile(cog_path, x=3, y=4, z=5)

    assert calls == [("open", str(cog_path)), ("tile", 3, 4, 5)]
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with MemoryFile(png) as memory_file:
            with memory_file.open() as dataset:
                decoded = np.moveaxis(dataset.read(), 0, -1)
    np.testing.assert_array_equal(
        decoded,
        np.array([[[213, 62, 79, 255], [0, 0, 0, 0]]], dtype=np.uint8),
    )


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
