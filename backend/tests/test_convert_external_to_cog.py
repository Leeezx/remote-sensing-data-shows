"""Tests for external-raster COG conversion planning and execution."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from scripts import convert_external_to_cog as converter


def _write_raster(
    path: Path,
    *,
    count: int,
    dtype: str = "uint16",
    nodata: int | float | None = 0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = np.arange(count * 32 * 32, dtype=dtype).reshape(count, 32, 32)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=32,
        width=32,
        count=count,
        dtype=dtype,
        crs="EPSG:4326",
        transform=from_origin(100, 40, 0.01, 0.01),
        nodata=nodata,
    ) as dataset:
        dataset.write(values)


def test_et_source_expands_to_46_zero_padded_single_band_jobs(tmp_path):
    source = tmp_path / "source" / "ET_2010.tif"
    _write_raster(source, count=46)
    config = converter.DatasetConfig(
        "et",
        source.parent,
        tmp_path / "destination",
        nodata=0,
    )

    jobs = converter.build_conversion_jobs(config, [source])

    assert len(jobs) == 46
    assert jobs[0].source == source
    assert jobs[0].destination.name == "2010_8day_01_cog.tif"
    assert jobs[0].indexes == (1,)
    assert jobs[-1].destination.name == "2010_8day_46_cog.tif"
    assert jobs[-1].indexes == (46,)
    assert all(job.overview_level == 5 for job in jobs)


@pytest.mark.parametrize("name", ["ET.tif", "ET_2010_2011.tif"])
def test_et_source_requires_exactly_one_year(name, tmp_path):
    source = tmp_path / name
    _write_raster(source, count=46)
    config = converter.DatasetConfig("et", tmp_path, tmp_path / "out", nodata=0)

    with pytest.raises(ValueError, match="exactly one year"):
        converter.build_conversion_jobs(config, [source])


def test_et_source_requires_exactly_46_bands(tmp_path):
    source = tmp_path / "ET_2010.tif"
    _write_raster(source, count=45)
    config = converter.DatasetConfig("et", tmp_path, tmp_path / "out", nodata=0)

    with pytest.raises(ValueError, match="46 bands"):
        converter.build_conversion_jobs(config, [source])


def test_et_sources_require_unique_years(tmp_path):
    first = tmp_path / "ET_2010.tif"
    second = tmp_path / "alternate_2010.tif"
    _write_raster(first, count=46)
    _write_raster(second, count=46)
    config = converter.DatasetConfig("et", tmp_path, tmp_path / "out", nodata=0)

    with pytest.raises(ValueError, match="Duplicate ET source year 2010"):
        converter.build_conversion_jobs(config, [first, second])


def test_soil_source_remains_one_all_band_conversion_job(tmp_path):
    source = tmp_path / "2010_13.tif"
    _write_raster(source, count=1, dtype="float32", nodata=-999)
    config = converter.DatasetConfig(
        "sm30",
        tmp_path,
        tmp_path / "out",
        nodata=-999,
        overview_resampling="nearest",
    )

    jobs = converter.build_conversion_jobs(config, [source])

    assert len(jobs) == 1
    assert jobs[0].destination == converter.output_path(source, config.default_destination)
    assert jobs[0].indexes is None
    assert jobs[0].overview_level is None


def test_et_source_and_destination_must_be_different(tmp_path):
    config = converter.DatasetConfig("et", tmp_path, tmp_path, nodata=0)

    with pytest.raises(ValueError, match="must be different"):
        converter.validate_conversion_roots(config)
