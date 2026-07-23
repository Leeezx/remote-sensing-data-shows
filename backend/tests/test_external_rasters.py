"""Tests for externally stored ET and layered soil-moisture rasters."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient

from backend.external_rasters import ExternalRasterSpec, RasterSource
from backend.main import app
from backend import external_rasters


client = TestClient(app)


def _write_raster(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[1],
        width=values.shape[2],
        count=values.shape[0],
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(100, 40, 1, 1),
        nodata=-999,
    ) as dataset:
        dataset.write(values.astype("float32"))


def test_discover_period_files_and_resolve_2010_13(monkeypatch, tmp_path):
    root = tmp_path / "sm10"
    _write_raster(root / "2010_13.tif", np.ones((1, 2, 2), dtype=np.float32))
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "sm_10cm",
        ExternalRasterSpec(root, "period_files"),
    )

    assert external_rasters.discover_external_times("sm_10cm") == ["2010-04-07"]
    source = external_rasters.resolve_external_raster("sm_10cm", "2010-04-07")
    assert source.path == (root / "2010_13.tif").resolve()
    assert source.band == 1


def test_resolve_sm10_8day_filename(monkeypatch, tmp_path):
    root = tmp_path / "sm10"
    _write_raster(
        root / "2010_8day_13_500m.tif",
        np.ones((1, 2, 2), dtype=np.float32),
    )
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "sm_10cm",
        ExternalRasterSpec(root, "period_files"),
    )

    source = external_rasters.resolve_external_raster("sm_10cm", "2010-04-07")
    assert source.path == (root / "2010_8day_13_500m.tif").resolve()


def test_resolve_uses_project_cog_even_when_it_contains_only_nodata(monkeypatch, tmp_path):
    cog_root = tmp_path / "cogs"
    _write_raster(
        cog_root / "2010_13_cog.tif",
        np.full((1, 128, 128), -999, dtype=np.float32),
    )
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "sm_30cm",
        ExternalRasterSpec(cog_root, "period_files"),
    )

    source = external_rasters.resolve_external_raster("sm_30cm", "2010-04-07")

    assert source.path == (cog_root / "2010_13_cog.tif").resolve()


def test_discover_single_period_et_files_and_resolve_band_one(
    monkeypatch, tmp_path
):
    root = tmp_path / "et"
    _write_raster(
        root / "2010_8day_01_cog.tif",
        np.ones((1, 2, 2), dtype=np.float32),
    )
    _write_raster(
        root / "2010_8day_02_cog.tif",
        np.full((1, 2, 2), 2, dtype=np.float32),
    )
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "et",
        ExternalRasterSpec(root, "period_files", 0.1, (0,)),
    )

    assert external_rasters.discover_external_times("et") == [
        "2010-01-01",
        "2010-01-09",
    ]
    source = external_rasters.resolve_external_raster("et", "2010-01-09")
    assert source.path == (root / "2010_8day_02_cog.tif").resolve()
    assert source.band == 1


def test_old_annual_et_file_is_not_discovered(monkeypatch, tmp_path):
    root = tmp_path / "et"
    _write_raster(
        root / "2010_cog.tif",
        np.ones((46, 2, 2), dtype=np.float32),
    )
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "et",
        ExternalRasterSpec(root, "period_files", 0.1, (0,)),
    )

    assert external_rasters.discover_external_times("et") == []
    with pytest.raises(FileNotFoundError, match="No raster found"):
        external_rasters.resolve_external_raster("et", "2010-01-01")


def test_default_et_runtime_spec_uses_period_files():
    assert external_rasters.EXTERNAL_RASTERS["et"].layout == "period_files"


def test_discover_period_sources_uses_explicit_root(tmp_path):
    root = tmp_path / "et"
    _write_raster(
        root / "2010_8day_01_cog.tif",
        np.ones((1, 2, 2), dtype=np.float32),
    )

    sources = external_rasters.discover_period_sources(root)

    assert list(sources) == ["2010-01-01"]
    assert sources["2010-01-01"] == RasterSource(
        (root / "2010_8day_01_cog.tif").resolve(), 1
    )


def test_external_point_query_uses_matching_band(monkeypatch, tmp_path):
    root = tmp_path / "et"
    _write_raster(
        root / "2010_8day_02_cog.tif",
        np.full((1, 2, 2), 42, dtype=np.float32),
    )
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "et",
        ExternalRasterSpec(root, "period_files"),
    )

    response = client.get(
        "/api/query/point",
        params={
            "layerId": "et",
            "time": "2010-01-09",
            "lng": 100.5,
            "lat": 39.5,
        },
    )

    assert response.status_code == 200
    assert response.json()["value"] == 42
    assert response.json()["unit"] == "mm/8天"


def test_external_point_query_applies_configured_value_scale(monkeypatch, tmp_path):
    root = tmp_path / "sm10"
    _write_raster(root / "2010_13.tif", np.full((1, 2, 2), 250, dtype=np.float32))
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "sm_10cm",
        ExternalRasterSpec(root, "period_files", value_scale=0.001),
    )

    response = client.get(
        "/api/query/point",
        params={
            "layerId": "sm_10cm",
            "time": "2010-04-07",
            "lng": 100.5,
            "lat": 39.5,
        },
    )

    assert response.status_code == 200
    assert response.json()["value"] == 0.25


def test_external_point_query_treats_zero_et_as_nodata(monkeypatch, tmp_path):
    root = tmp_path / "et"
    _write_raster(
        root / "2010_8day_01_cog.tif", np.zeros((1, 2, 2), dtype=np.float32)
    )
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "et",
        ExternalRasterSpec(root, "period_files", 0.1, (0,)),
    )

    response = client.get(
        "/api/query/point",
        params={
            "layerId": "et",
            "time": "2010-01-01",
            "lng": 100.5,
            "lat": 39.5,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "No valid data at this point"


def test_external_tile_route_renders_matching_band(monkeypatch, tmp_path):
    root = tmp_path / "sm10"
    _write_raster(
        root / "2010_13.tif",
        np.full((1, 2, 2), 0.25, dtype=np.float32),
    )
    monkeypatch.setitem(
        external_rasters.EXTERNAL_RASTERS,
        "sm_10cm",
        ExternalRasterSpec(root, "period_files"),
    )

    response = client.get(
        "/data/raster-tiles/sm_10cm/WebMercatorQuad/4/12/6.png",
        params={"time": "2010-04-07"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == (
        "public, max-age=604800, immutable"
    )
    assert response.content.startswith(b"\x89PNG")
