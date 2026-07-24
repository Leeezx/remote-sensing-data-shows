# ET Single-Period COG and Precomputed Legends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four pixel-interleaved, 46-band annual ET COGs with 184 single-period, single-band COGs and serve ET legends exclusively from a validated precomputed JSON file.

**Architecture:** The offline converter will create one atomic, validated COG per annual source band while preserving the existing conversion interface used by soil-moisture rebuilds. Runtime raster discovery will treat ET exactly like the existing period-file layers and always read band 1. A focused ET legend module will own percentile construction, strict JSON validation, file-signature caching, and defensive reads; a separate offline command will sample the new COG overviews and atomically publish all legends.

**Tech Stack:** Python 3.12, FastAPI, pytest, NumPy, rasterio/GDAL, rio-cogeo, rio-tiler

## Global Constraints

- Do not modify Nginx caching, Docker Compose resource limits, or the two-worker production configuration.
- Do not change frontend URLs, FastAPI endpoint paths, ET display scale `0.1`, ET unit `mm/8天`, ET zero-as-NoData behavior, or the six-color palette.
- Runtime ET support is strict period-file support; do not retain or add an annual 46-band fallback.
- Period files are named `YYYY_8day_PP_cog.tif`, where `PP` is zero-padded `01` through `46`.
- Every ET destination is a single-band, `uint16`, NoData `0`, tiled, `512×512`, band-interleaved, DEFLATE COG with average overviews through factor 32.
- The converter must never delete or overwrite an annual source file and must reject identical ET source and destination directories.
- ET legends are stored in `data/stats/et_legends.json`, keyed by ISO 8-day date, with schema version `1`.
- Runtime legend failures must return an explicit service-unavailable response; runtime code must never sample a raster or silently fall back to dynamic legend computation.
- Generated ET files must be uploaded before deploying the strict new backend; old annual files are deleted manually only after production verification.
- Preserve unrelated user-owned working-tree changes and stage only exact task files.

## File Structure

- Create `backend/et_legends.py`: ET percentile construction, document validation, file-signature cache, defensive legend lookup, and `ETLegendUnavailableError`.
- Create `backend/precompute_et_legends.py`: offline overview sampling, all-or-nothing document construction, atomic JSON publication, and CLI.
- Create `backend/tests/test_convert_external_to_cog.py`: conversion-job planning, safety, atomic write, COG structure, and soil compatibility.
- Create `backend/tests/test_et_legends.py`: ET mask/percentile behavior and strict runtime JSON cache tests.
- Create `backend/tests/test_precompute_et_legends.py`: offline sampling, fallback warning, deterministic document, and atomic publication tests.
- Modify `scripts/convert_external_to_cog.py`: add ET per-band jobs and atomic validated single-band conversion without breaking `convert_one(...)` callers.
- Modify `backend/external_rasters.py`: configure ET as a period-file source, expose explicit-root period discovery for the precomputer, and remove ET dynamic raster sampling.
- Modify `backend/routers/layers.py`: use the precomputed ET legend after resolving the requested period file.
- Modify `backend/routers/tiles.py`: pass the request time into ET rendering, use the precomputed legend, and translate legend availability failures to HTTP 503.
- Modify `backend/tests/test_external_rasters.py`: replace annual ET contracts with single-period band-1 contracts and prove old annual files are ignored.
- Modify `backend/tests/test_layers.py`: assert time-keyed precomputed legend use and 503 failure behavior.
- Modify `backend/tests/test_tiles.py`: assert ET tile rendering uses precomputed legends without dynamic raster sampling and returns 503 for legend failures.
- Modify `data/metadata/layers.json`: describe ET as one single-band COG per 8-day period.
- Generate `data/stats/et_legends.json`: deterministic legends for the 184 real ET periods after local conversion.

---

### Task 1: Strict ET period-file runtime contract

**Files:**
- Modify: `backend/tests/test_external_rasters.py`
- Modify: `backend/external_rasters.py`
- Modify: `data/metadata/layers.json`
- Modify: `backend/tests/test_layers.py`

**Interfaces:**
- Consumes: Existing `_PERIOD_FILE`, `_period_date(...)`, `discover_external_times(layer_id)`, and `resolve_external_raster(layer_id, time)`.
- Produces: `discover_period_sources(root: Path, *, reject_duplicates: bool = False) -> dict[str, RasterSource]`; ET `RasterSource` values always have `band == 1`.

- [ ] **Step 1: Replace the annual ET discovery test with strict period-file tests**

Replace `test_discover_annual_et_bands` in `backend/tests/test_external_rasters.py` with:

```python
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
```

Add `import pytest` at the top of the test file and import `RasterSource`
beside `ExternalRasterSpec`.

Also add:

```python
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
```

- [ ] **Step 2: Change the ET point-query fixtures to single-period files**

In `test_external_point_query_uses_matching_band`, replace the two-band annual
fixture with:

```python
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
```

In `test_external_point_query_treats_zero_et_as_nodata`, use
`root / "2010_8day_01_cog.tif"` and `ExternalRasterSpec(root, "period_files", 0.1, (0,))`.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest `
  backend/tests/test_external_rasters.py::test_discover_single_period_et_files_and_resolve_band_one `
  backend/tests/test_external_rasters.py::test_old_annual_et_file_is_not_discovered `
  backend/tests/test_external_rasters.py::test_default_et_runtime_spec_uses_period_files `
  backend/tests/test_external_rasters.py::test_discover_period_sources_uses_explicit_root `
  backend/tests/test_external_rasters.py::test_external_point_query_uses_matching_band `
  backend/tests/test_external_rasters.py::test_external_point_query_treats_zero_et_as_nodata `
  -v -p no:cacheprovider
```

Expected: the default-spec test fails because ET is still configured for
annual bands, and the explicit-root test fails because
`discover_period_sources(...)` does not exist.

- [ ] **Step 4: Add explicit-root period discovery and configure ET as a period source**

In `backend/external_rasters.py`, add:

```python
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
    return {
        _period_date(year, period).isoformat(): RasterSource(
            path=paths[0].resolve(),
            band=1,
        )
        for (year, period), paths in sorted(candidates.items())
    }
```

Change the ET entry to:

```python
"et": _external_spec("et", "period_files", 0.1, (0,)),
```

The generic annual helper may remain as an internal utility, but no active ET
configuration or route may select it.

- [ ] **Step 5: Update ET metadata and add a regression assertion**

Change the ET description in `data/metadata/layers.json` to:

```json
"description": "500m ET data with one single-band Cloud-Optimized GeoTIFF per 8-day period",
```

Append to `backend/tests/test_layers.py`:

```python
def test_et_metadata_describes_single_period_cogs():
    layer = next(item for item in client.get("/api/layers").json() if item["id"] == "et")

    assert "single-band" in layer["description"]
    assert "per 8-day period" in layer["description"]
    assert "annual GeoTIFF" not in layer["description"]
```

- [ ] **Step 6: Run Task 1 tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest `
  backend/tests/test_external_rasters.py `
  backend/tests/test_layers.py::test_et_metadata_describes_single_period_cogs `
  -v -p no:cacheprovider
```

Expected: all selected tests pass; ET resolves period files with band 1 and an
annual-only directory yields no ET times.

- [ ] **Step 7: Commit the strict runtime layout**

```powershell
git add -- `
  backend/tests/test_external_rasters.py `
  backend/external_rasters.py `
  backend/tests/test_layers.py `
  data/metadata/layers.json
git commit -m "feat: require single-period ET rasters"
```

---

### Task 2: ET per-band conversion job planning and safety

**Files:**
- Create: `backend/tests/test_convert_external_to_cog.py`
- Modify: `scripts/convert_external_to_cog.py`

**Interfaces:**
- Consumes: Existing `DatasetConfig`, `collect_sources(...)`, `output_path(...)`, and CLI `--dataset/--src/--dst`.
- Produces: `ConversionJob`; `source_year(source: Path) -> int`; `et_output_path(source: Path, destination: Path, band: int) -> Path`; `build_conversion_jobs(config: DatasetConfig, sources: list[Path]) -> list[ConversionJob]`.

- [ ] **Step 1: Write failing job-planning tests**

Create `backend/tests/test_convert_external_to_cog.py` with:

```python
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
```

- [ ] **Step 2: Run the planning tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_convert_external_to_cog.py -v -p no:cacheprovider
```

Expected: test failures when the test functions access `ConversionJob` and
`build_conversion_jobs(...)`; test collection itself succeeds.

- [ ] **Step 3: Add the conversion-job model and ET naming rules**

In `scripts/convert_external_to_cog.py`, add:

```python
import re
from typing import Sequence


ET_PERIODS_PER_YEAR = 46
ET_OVERVIEW_LEVEL = 5


@dataclass(frozen=True)
class ConversionJob:
    source: Path
    destination: Path
    nodata: float | None
    overview_resampling: str
    indexes: tuple[int, ...] | None = None
    overview_level: int | None = None


def source_year(source: Path) -> int:
    years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", source.stem)
    if len(years) != 1:
        raise ValueError(
            f"ET source '{source.name}' must contain exactly one year"
        )
    return int(years[0])


def et_output_path(source: Path, destination: Path, band: int) -> Path:
    year = source_year(source)
    return destination / f"{year}_8day_{band:02d}_cog.tif"
```

Add:

```python
def build_conversion_jobs(
    config: DatasetConfig, sources: list[Path]
) -> list[ConversionJob]:
    jobs: list[ConversionJob] = []
    et_years: set[int] = set()
    for source in sources:
        if config.key == "et":
            year = source_year(source)
            if year in et_years:
                raise ValueError(f"Duplicate ET source year {year}")
            et_years.add(year)
            with rasterio.open(source) as dataset:
                count = dataset.count
            if count != ET_PERIODS_PER_YEAR:
                raise ValueError(
                    f"ET source '{source.name}' must contain exactly 46 bands; "
                    f"found {count}"
                )
            for band in range(1, ET_PERIODS_PER_YEAR + 1):
                jobs.append(
                    ConversionJob(
                        source=source,
                        destination=et_output_path(
                            source, config.default_destination, band
                        ),
                        nodata=config.nodata,
                        overview_resampling=config.overview_resampling,
                        indexes=(band,),
                        overview_level=ET_OVERVIEW_LEVEL,
                    )
                )
            continue
        jobs.append(
            ConversionJob(
                source=source,
                destination=output_path(source, config.default_destination),
                nodata=config.nodata,
                overview_resampling=config.overview_resampling,
            )
        )
    return jobs
```

Import `rasterio` at module scope. Remove the unused `Sequence` import if the
implementation does not need it.

- [ ] **Step 4: Reject identical ET source and destination directories**

Add:

```python
def validate_conversion_roots(config: DatasetConfig) -> None:
    if (
        config.key == "et"
        and config.source.resolve() == config.default_destination.resolve()
    ):
        raise ValueError(
            "ET source and destination directories must be different"
        )
```

Append this test:

```python
def test_et_source_and_destination_must_be_different(tmp_path):
    config = converter.DatasetConfig("et", tmp_path, tmp_path, nodata=0)

    with pytest.raises(ValueError, match="must be different"):
        converter.validate_conversion_roots(config)
```

Call `validate_conversion_roots(config)` for every selected config before
collecting sources in `main()`.

Update the module usage examples so ET always supplies distinct `--src` and
`--dst` directories. The example must use:

```text
python scripts/convert_external_to_cog.py --dataset et \
  --src data/rasters/et --dst data/rasters/et_period --workers 1
```

- [ ] **Step 5: Run the planning and safety tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_convert_external_to_cog.py -v -p no:cacheprovider
```

Expected: all job-planning and root-safety tests pass.

- [ ] **Step 6: Commit conversion planning**

```powershell
git add -- `
  backend/tests/test_convert_external_to_cog.py `
  scripts/convert_external_to_cog.py
git commit -m "feat: plan single-period ET conversions"
```

---

### Task 3: Atomic validated single-band COG conversion

**Files:**
- Modify: `backend/tests/test_convert_external_to_cog.py`
- Modify: `scripts/convert_external_to_cog.py`
- Verify: `scripts/rebuild_deep_soil_cogs.py`

**Interfaces:**
- Consumes: `ConversionJob` from Task 2 and the legacy
  `convert_one(source, destination, nodata, overview_resampling)` call used by
  `rebuild_deep_soil_cogs.py`.
- Produces: backward-compatible
  `convert_one(source, destination, nodata, overview_resampling="average", indexes=None, overview_level=None) -> tuple[str, bool, str]`;
  `destination_is_complete(job: ConversionJob) -> bool`;
  `run_conversion_job(job: ConversionJob) -> tuple[str, bool, str]`.

- [ ] **Step 1: Write the real single-band COG test**

Append:

```python
def test_et_job_writes_atomic_valid_single_band_cog(tmp_path):
    from rio_cogeo.cogeo import cog_validate

    source = tmp_path / "source" / "ET_2010.tif"
    _write_raster(source, count=46)
    destination = tmp_path / "out" / "2010_8day_02_cog.tif"
    job = converter.ConversionJob(
        source=source,
        destination=destination,
        nodata=0,
        overview_resampling="average",
        indexes=(2,),
        overview_level=5,
    )

    name, ok, error = converter.run_conversion_job(job)

    assert (name, ok, error) == (source.name, True, "")
    assert destination.is_file()
    assert list(destination.parent.glob(f".{destination.name}.*.tmp.tif")) == []
    valid, errors, _warnings = cog_validate(destination)
    assert valid, errors
    with rasterio.open(destination) as dataset:
        assert dataset.count == 1
        assert dataset.dtypes == ("uint16",)
        assert dataset.nodata == 0
        assert dataset.is_tiled
        assert dataset.block_shapes == [(512, 512)]
        assert dataset.profile["interleave"] == "band"
        assert dataset.overviews(1) == [2, 4, 8, 16, 32]
        expected = rasterio.open(source).read(2)
        np.testing.assert_array_equal(dataset.read(1), expected)
```

Change `_write_raster` in this test file to accept optional `height` and
`width` arguments and create a `512×512` source for this one test so five
overview levels can be created without making every planning test large. Close
the source dataset with a `with` block when reading `expected`.

- [ ] **Step 2: Write atomic-failure and completion tests**

Append:

```python
def test_failed_conversion_does_not_replace_existing_destination(
    monkeypatch, tmp_path
):
    source = tmp_path / "ET_2010.tif"
    _write_raster(source, count=46)
    destination = tmp_path / "out" / "2010_8day_01_cog.tif"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"previous")
    job = converter.ConversionJob(
        source, destination, 0, "average", (1,), 5
    )

    def fail_translate(*_args, **_kwargs):
        raise RuntimeError("injected conversion failure")

    monkeypatch.setattr(converter, "_translate_cog", fail_translate)

    _name, ok, error = converter.run_conversion_job(job)

    assert not ok
    assert "injected conversion failure" in error
    assert destination.read_bytes() == b"previous"
    assert list(destination.parent.glob(f".{destination.name}.*.tmp.tif")) == []


def test_complete_destination_is_skipped_unless_forced(tmp_path):
    source = tmp_path / "source" / "ET_2010.tif"
    _write_raster(source, count=46)
    destination = tmp_path / "out" / "2010_8day_01_cog.tif"
    job = converter.ConversionJob(
        source, destination, 0, "average", (1,), 5
    )
    assert converter.run_conversion_job(job)[1]

    assert converter.destination_is_complete(job)
    assert not converter.needs_job_conversion(job, force=False)
    assert converter.needs_job_conversion(job, force=True)
```

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest `
  backend/tests/test_convert_external_to_cog.py::test_et_job_writes_atomic_valid_single_band_cog `
  backend/tests/test_convert_external_to_cog.py::test_failed_conversion_does_not_replace_existing_destination `
  backend/tests/test_convert_external_to_cog.py::test_complete_destination_is_skipped_unless_forced `
  -v -p no:cacheprovider
```

Expected: failures because atomic temporary writes, structure validation, and
job-aware skip logic are not implemented.

- [ ] **Step 4: Isolate rio-cogeo translation and preserve the legacy signature**

Move the rio-cogeo call behind:

```python
def _translate_cog(
    source: Path,
    destination: Path,
    profile: dict,
    *,
    indexes: tuple[int, ...] | None,
    nodata: float | None,
    overview_level: int | None,
    overview_resampling: str,
) -> None:
    from rio_cogeo.cogeo import cog_translate

    cog_translate(
        str(source),
        str(destination),
        profile,
        indexes=indexes,
        add_mask=True,
        nodata=nodata,
        overview_level=overview_level,
        overview_resampling=overview_resampling,
        quiet=True,
    )
```

Extend, but do not replace, the existing public signature:

```python
def convert_one(
    source: Path,
    destination: Path,
    nodata: float | None,
    overview_resampling: str = "average",
    indexes: tuple[int, ...] | None = None,
    overview_level: int | None = None,
) -> tuple[str, bool, str]:
```

This keeps every four-argument call in `scripts/rebuild_deep_soil_cogs.py`
valid.

- [ ] **Step 5: Implement atomic translation and validation**

Inside `convert_one(...)`, build the existing DEFLATE profile and add:

```python
profile["blockxsize"] = COG_BLOCKSIZE
profile["blockysize"] = COG_BLOCKSIZE
profile["interleave"] = "band"
```

Use a unique sibling temporary path:

```python
temporary = destination.with_name(
    f".{destination.name}.{uuid.uuid4().hex}.tmp.tif"
)
```

Create the parent, translate to `temporary`, validate with
`cog_validate(temporary)`, open it with rasterio, and check `count == 1` when
`indexes` selects one band. Only then call `os.replace(temporary, destination)`.
In `except`, unlink only `temporary` and return the existing
`(source.name, False, str(exc))` result. Never unlink `destination`.

Add:

```python
def run_conversion_job(job: ConversionJob) -> tuple[str, bool, str]:
    return convert_one(
        job.source,
        job.destination,
        job.nodata,
        job.overview_resampling,
        job.indexes,
        job.overview_level,
    )
```

- [ ] **Step 6: Add job-aware completion validation**

Implement `destination_is_complete(job)` by checking:

- destination exists;
- `cog_validate(...)` is valid;
- CRS, width, and height match the source;
- output is tiled with `512×512` blocks;
- one-band ET jobs have `count == 1`, NoData `0`, band interleave, and
  `dtype == uint16`, `[2, 4, 8, 16, 32]` overviews;
- non-ET/all-band jobs retain the existing count expectation.

Implement:

```python
def needs_job_conversion(job: ConversionJob, force: bool = False) -> bool:
    if force or not destination_is_complete(job):
        return True
    return job.source.stat().st_mtime > job.destination.stat().st_mtime
```

Use `build_conversion_jobs(...)`, `needs_job_conversion(...)`, and
`run_conversion_job(...)` in `main()`. Keep `--limit` operating on expanded
jobs so `--limit 1` converts exactly one ET period. Move dry-run output after
job expansion so it reports the exact job count and first planned destination
names without writing files.

- [ ] **Step 7: Run Task 3 tests and the deep-soil compatibility smoke test**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_convert_external_to_cog.py -v -p no:cacheprovider
python scripts/rebuild_deep_soil_cogs.py --dry-run --limit 1
```

Expected: all converter tests pass; the deep-soil command lists one planned
overwrite and exits 0 without a `TypeError`.

- [ ] **Step 8: Commit atomic conversion**

```powershell
git add -- `
  backend/tests/test_convert_external_to_cog.py `
  scripts/convert_external_to_cog.py
git commit -m "feat: write atomic single-band ET COGs"
```

---

### Task 4: Strict ET legend construction and runtime cache

**Files:**
- Create: `backend/et_legends.py`
- Create: `backend/tests/test_et_legends.py`

**Interfaces:**
- Produces: `ETLegendUnavailableError`; `build_et_legend(values, base_legend, unit, *, source_mask=None, nodata=None, value_scale=0.1, nodata_values=(0,)) -> list[dict]`; `validate_et_legend_document(document) -> dict[str, tuple[tuple[float, str, str], ...]]`; `get_precomputed_et_legend(time: str, path: Path | None = None) -> list[dict]`.

- [ ] **Step 1: Write failing construction tests**

Create `backend/tests/test_et_legends.py` with:

```python
import importlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

BASE_LEGEND = [
    {"value": 0, "color": "#d53e4f", "label": "低"},
    {"value": 20, "color": "#fc8d59", "label": "较低"},
    {"value": 40, "color": "#fee08b", "label": "中等"},
    {"value": 60, "color": "#99d594", "label": "较高"},
    {"value": 80, "color": "#3288bd", "label": "高"},
    {"value": 100, "color": "#016c59", "label": "很高"},
]


def _et_legends():
    return importlib.import_module("backend.et_legends")


def test_build_et_legend_masks_invalid_raw_values_before_scaling():
    et_legends = _et_legends()
    values = np.array([0, 100, 200, 300, 400, 500, 600, -999, np.nan])
    source_mask = np.array([255, 255, 255, 255, 255, 255, 255, 255, 255])

    result = et_legends.build_et_legend(
        values,
        BASE_LEGEND,
        "mm/8天",
        source_mask=source_mask,
        nodata=-999,
        value_scale=0.1,
        nodata_values=(0,),
    )

    expected = np.percentile(
        np.array([10, 20, 30, 40, 50, 60], dtype=float),
        np.linspace(2, 98, 6),
    )
    np.testing.assert_allclose([item["value"] for item in result], expected)
    assert [item["color"] for item in result] == [
        item["color"] for item in BASE_LEGEND
    ]
    assert all(item["label"].endswith("mm/8天") for item in result)


def test_build_et_legend_falls_back_when_six_distinct_stops_are_impossible():
    et_legends = _et_legends()
    result = et_legends.build_et_legend(
        np.ones(100),
        BASE_LEGEND,
        "mm/8天",
    )

    assert result == BASE_LEGEND
    assert result is not BASE_LEGEND
```

- [ ] **Step 2: Write failing JSON validation and cache tests**

Append:

```python
def _document(value_offset: float = 0) -> dict:
    return {
        "version": 1,
        "legends": {
            "2010-01-01": [
                {
                    "value": value_offset + index + 1,
                    "color": item["color"],
                    "label": f"{value_offset + index + 1:.1f} mm/8天",
                }
                for index, item in enumerate(BASE_LEGEND)
            ]
        },
    }


def test_get_precomputed_et_legend_reuses_file_cache_and_returns_copies(
    monkeypatch, tmp_path
):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")
    reads = []
    original = Path.read_text

    def tracked_read(self, *args, **kwargs):
        reads.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracked_read)

    first = et_legends.get_precomputed_et_legend("2010-01-01", path)
    first[0]["value"] = -1
    second = et_legends.get_precomputed_et_legend("2010-01-01", path)

    assert second[0]["value"] == 1
    assert reads == [path.resolve()]


def test_get_precomputed_et_legend_refreshes_after_atomic_replacement(tmp_path):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    replacement = tmp_path / "replacement.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")
    first = et_legends.get_precomputed_et_legend("2010-01-01", path)
    replacement.write_text(json.dumps(_document(10)), encoding="utf-8")
    os.replace(replacement, path)

    second = et_legends.get_precomputed_et_legend("2010-01-01", path)

    assert first[0]["value"] == 1
    assert second[0]["value"] == 11


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"version": 2, "legends": {}}, "Unsupported ET legend version"),
        ({"version": 1, "legends": []}, "legends must be an object"),
        (
            {"version": 1, "legends": {"2010-01-01": []}},
            "must contain exactly 6 items",
        ),
    ],
)
def test_invalid_et_legend_document_is_rejected(document, message, tmp_path):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(et_legends.ETLegendUnavailableError, match=message):
        et_legends.get_precomputed_et_legend("2010-01-01", path)


def test_missing_time_is_rejected_without_dynamic_fallback(tmp_path):
    et_legends = _et_legends()
    path = tmp_path / "et_legends.json"
    path.write_text(json.dumps(_document()), encoding="utf-8")

    with pytest.raises(
        et_legends.ETLegendUnavailableError,
        match="No precomputed ET legend for time '2010-01-09'",
    ):
        et_legends.get_precomputed_et_legend("2010-01-09", path)
```

- [ ] **Step 3: Run the legend tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_et_legends.py -v -p no:cacheprovider
```

Expected: test failures at `_et_legends()` because `backend.et_legends` does
not exist; test collection itself succeeds.

- [ ] **Step 4: Implement ET percentile construction**

Create `backend/et_legends.py`. Use `valid_data_mask` from
`backend.raster_rendering`, apply raw NoData and layer-specific zero checks
before multiplying valid values by `value_scale`, and compute:

```python
stops = np.percentile(valid_values, np.linspace(2, 98, 6))
```

Return defensive copies of `base_legend` when it is not six items, fewer than
six positive finite values remain, percentile values are not finite, or stops
are not strictly increasing. Otherwise preserve the six base colors and format
labels as `f"{value:.1f} {unit}".strip()`.

- [ ] **Step 5: Implement strict document validation**

Define:

```python
class ETLegendUnavailableError(RuntimeError):
    """The persisted ET legend document cannot serve the requested time."""
```

`validate_et_legend_document(...)` must reject:

- non-dictionary roots;
- `version != 1`;
- a non-dictionary `legends`;
- invalid ISO date keys;
- entries that are not six-item lists;
- non-dictionary items;
- booleans or non-numeric/non-finite values;
- non-string colors or labels;
- non-strictly-increasing values.

Return immutable tuples keyed by the original ISO strings.

- [ ] **Step 6: Implement signature-keyed cached loading**

Define `ET_LEGEND_CACHE_PATH` from the project root. Implement an
`@lru_cache(maxsize=4)` loader keyed by resolved path text, `st_mtime_ns`, and
`st_size`. Guard cold loads with a module `threading.Lock`, wrap file/stat/JSON
errors in `ETLegendUnavailableError`, and return fresh dictionaries from
`get_precomputed_et_legend(...)`.

The optional `path` argument must default to `None`, then resolve
`ET_LEGEND_CACHE_PATH` inside the function so tests and deployment overrides do
not suffer from a definition-time `Path` default.

- [ ] **Step 7: Run Task 4 tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_et_legends.py -v -p no:cacheprovider
```

Expected: all ET construction, validation, refresh, and defensive-copy tests
pass.

- [ ] **Step 8: Commit the ET legend module**

```powershell
git add -- backend/et_legends.py backend/tests/test_et_legends.py
git commit -m "feat: add strict precomputed ET legends"
```

---

### Task 5: All-or-nothing ET legend precomputation

**Files:**
- Create: `backend/precompute_et_legends.py`
- Create: `backend/tests/test_precompute_et_legends.py`
- Modify: `backend/external_rasters.py`

**Interfaces:**
- Consumes: `discover_period_sources(...)` from Task 1 and
  `build_et_legend(...)` from Task 4.
- Produces: `read_et_sample(source: RasterSource) -> tuple[np.ndarray, np.ndarray, float | None]`; `build_et_legend_document(root: Path, base_legend: list[dict], unit: str) -> dict`; `write_et_legend_document(document: dict, output: Path) -> None`; CLI options `--root PATH` and `--output PATH`.

- [ ] **Step 1: Write failing document-generation tests**

Create `backend/tests/test_precompute_et_legends.py` with:

```python
import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

BASE_LEGEND = [
    {"value": 0, "color": "#d53e4f", "label": "低"},
    {"value": 20, "color": "#fc8d59", "label": "较低"},
    {"value": 40, "color": "#fee08b", "label": "中等"},
    {"value": 60, "color": "#99d594", "label": "较高"},
    {"value": 80, "color": "#3288bd", "label": "高"},
    {"value": 100, "color": "#016c59", "label": "很高"},
]


def _precomputer():
    return importlib.import_module("backend.precompute_et_legends")


def _write_period(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(100, 40, 0.01, 0.01),
        nodata=0,
        tiled=True,
        blockxsize=16,
        blockysize=16,
    ) as dataset:
        dataset.write(values.astype("uint16"), 1)


def test_build_document_is_sorted_complete_and_scaled(tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    values = np.arange(1, 257, dtype=np.uint16).reshape(16, 16)
    _write_period(root / "2010_8day_02_cog.tif", values + 10)
    _write_period(root / "2010_8day_01_cog.tif", values)

    document = precompute_et_legends.build_et_legend_document(
        root, BASE_LEGEND, "mm/8天"
    )

    assert document["version"] == 1
    assert list(document["legends"]) == ["2010-01-01", "2010-01-09"]
    assert len(document["legends"]["2010-01-01"]) == 6
    assert document["legends"]["2010-01-01"][0]["value"] < 10


def test_duplicate_period_files_are_a_hard_failure(tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    values = np.arange(1, 257, dtype=np.uint16).reshape(16, 16)
    _write_period(root / "2010_01_cog.tif", values)
    _write_period(root / "2010_8day_01_cog.tif", values)

    with pytest.raises(ValueError, match="Duplicate raster files"):
        precompute_et_legends.build_et_legend_document(
            root, BASE_LEGEND, "mm/8天"
        )
```

- [ ] **Step 2: Write fallback-warning and atomic-publication tests**

Append:

```python
def test_constant_period_uses_base_legend_and_logs_warning(caplog, tmp_path):
    precompute_et_legends = _precomputer()
    root = tmp_path / "et"
    _write_period(
        root / "2010_8day_01_cog.tif",
        np.ones((16, 16), dtype=np.uint16),
    )

    document = precompute_et_legends.build_et_legend_document(
        root, BASE_LEGEND, "mm/8天"
    )

    assert document["legends"]["2010-01-01"] == BASE_LEGEND
    assert "base legend" in caplog.text


def test_atomic_write_preserves_previous_document_on_failure(
    monkeypatch, tmp_path
):
    precompute_et_legends = _precomputer()
    output = tmp_path / "stats" / "et_legends.json"
    output.parent.mkdir(parents=True)
    output.write_text('{"previous": true}', encoding="utf-8")

    def fail_replace(*_args):
        raise OSError("injected replace failure")

    monkeypatch.setattr(precompute_et_legends.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        precompute_et_legends.write_et_legend_document(
            {"version": 1, "legends": {}}, output
        )

    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []
```

- [ ] **Step 3: Run the precompute tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_precompute_et_legends.py -v -p no:cacheprovider
```

Expected: test failures at `_precomputer()` because the offline module does
not exist; test collection itself succeeds.

- [ ] **Step 4: Make explicit-root discovery reject duplicates**

In `discover_period_sources(...)`, use `_period_file_candidates(...)` and honor
`reject_duplicates=True` exactly as defined in Task 1. The precomputer must call:

```python
sources = discover_period_sources(root, reject_duplicates=True)
```

An empty source mapping raises
`ValueError(f"No ET period rasters found under '{root}'")`.

- [ ] **Step 5: Implement overview-aware sample reading**

Create `backend/precompute_et_legends.py`. In `read_et_sample(...)`, open the
source path and read band 1 to:

```python
height = min(dataset.height, 512)
width = min(dataset.width, 512)
```

Use `Resampling.average` for values and `Resampling.nearest` for masks. Return
the raw values, mask, and raw dataset NoData without applying the `0.1` scale;
`build_et_legend(...)` owns scale and validity ordering.

- [ ] **Step 6: Build and validate the complete deterministic document**

For every sorted `(time, source)`:

1. read the sample;
2. call `build_et_legend(..., value_scale=0.1, nodata_values=(0,))`;
3. log a warning when the result equals defensive copies of the base values
   because usable distinct percentiles were unavailable;
4. insert the six entries under the ISO time.

Construct `{"version": 1, "legends": legends}`, call
`validate_et_legend_document(...)`, and only then return it.

- [ ] **Step 7: Implement atomic JSON publication and CLI**

`write_et_legend_document(...)` must create the parent, write UTF-8
`json.dumps(..., ensure_ascii=False, indent=2) + "\n"` to a unique sibling
temporary file, flush and `os.fsync`, then `os.replace`. On any exception,
unlink only the temporary file.

The CLI must use `argparse` options:

```text
--root   default: data/rasters/et
--output default: data/stats/et_legends.json
```

It must load ET base metadata with `get_layer("et")`, fail if metadata or its
legend is missing, print the source count and output path, and exit nonzero on
any hard failure.

- [ ] **Step 8: Run Task 5 tests and CLI help**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests/test_precompute_et_legends.py -v -p no:cacheprovider
python -m backend.precompute_et_legends --help
```

Expected: all precompute tests pass; help shows `--root` and `--output`.

- [ ] **Step 9: Commit the precomputer**

```powershell
git add -- `
  backend/precompute_et_legends.py `
  backend/tests/test_precompute_et_legends.py `
  backend/external_rasters.py
git commit -m "feat: precompute ET legends atomically"
```

---

### Task 6: Route ET tiles and metadata through precomputed legends

**Files:**
- Modify: `backend/routers/layers.py`
- Modify: `backend/routers/tiles.py`
- Modify: `backend/external_rasters.py`
- Modify: `backend/tests/test_layers.py`
- Modify: `backend/tests/test_tiles.py`
- Modify: `backend/tests/test_external_rasters.py`

**Interfaces:**
- Consumes: `get_precomputed_et_legend(time)` and
  `ETLegendUnavailableError` from Task 4.
- Produces: unchanged successful response bodies; HTTP 503 detail
  `ET legend is unavailable for time '<time>'` when the persisted legend cannot serve the time.

- [ ] **Step 1: Replace the ET layer-legend route test**

Replace `test_get_et_legend_uses_the_resolved_time_source` in
`backend/tests/test_layers.py` with:

```python
def test_get_et_legend_uses_precomputed_time_entry(monkeypatch, tmp_path):
    et_path = tmp_path / "2010_8day_01_cog.tif"
    et_path.touch()
    dynamic_legend = [
        {"value": 12.3, "color": "#d53e4f", "label": "12.3 mm/8天"}
    ]
    calls = []
    monkeypatch.setattr(
        layers_router,
        "get_layer",
        lambda layer_id: {
            "id": layer_id,
            "unit": "mm/8天",
            "legend": [{"value": 0, "color": "#d53e4f", "label": "低"}],
        },
    )
    monkeypatch.setattr(
        layers_router,
        "resolve_external_raster",
        lambda *_args: RasterSource(et_path, 1),
    )
    monkeypatch.setattr(
        layers_router,
        "get_precomputed_et_legend",
        lambda time: calls.append(time) or dynamic_legend,
    )

    response = client.get(
        "/api/layers/et/legend", params={"time": "2010-01-01"}
    )

    assert response.status_code == 200
    assert response.json()["legend"] == dynamic_legend
    assert calls == ["2010-01-01"]
```

Append:

```python
def test_get_et_legend_returns_503_when_precomputed_entry_is_unavailable(
    monkeypatch, tmp_path
):
    et_path = tmp_path / "2010_8day_01_cog.tif"
    et_path.touch()
    monkeypatch.setattr(
        layers_router,
        "get_layer",
        lambda layer_id: {
            "id": layer_id,
            "unit": "mm/8天",
            "legend": [{"value": 0, "color": "#d53e4f", "label": "低"}],
        },
    )
    monkeypatch.setattr(
        layers_router,
        "resolve_external_raster",
        lambda *_args: RasterSource(et_path, 1),
    )

    def unavailable(_time):
        raise ETLegendUnavailableError("missing test entry")

    monkeypatch.setattr(
        layers_router, "get_precomputed_et_legend", unavailable
    )

    response = client.get(
        "/api/layers/et/legend", params={"time": "2010-01-01"}
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "ET legend is unavailable for time '2010-01-01'"
    )
```

Import `ETLegendUnavailableError` from `backend.et_legends`.

- [ ] **Step 2: Add ET tile route tests**

Append to `backend/tests/test_tiles.py`:

```python
def test_render_et_tile_uses_precomputed_time_legend(monkeypatch, tmp_path):
    source = RasterSource(tmp_path / "2010_8day_01_cog.tif", 1)
    expected = [{"value": 1, "color": "#d53e4f", "label": "1.0 mm/8天"}]
    calls = []
    monkeypatch.setattr(
        tiles,
        "get_layer",
        lambda layer_id: {
            "id": layer_id,
            "unit": "mm/8天",
            "legend": expected,
        },
    )
    monkeypatch.setattr(
        tiles,
        "get_precomputed_et_legend",
        lambda time: calls.append(time) or expected,
    )

    class FakeReader:
        def __init__(self, _path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def tile(self, *_args, **_kwargs):
            return SimpleNamespace(
                data=np.ones((1, 2, 2), dtype=np.uint16),
                mask=np.full((2, 2), 255, dtype=np.uint8),
            )

    monkeypatch.setattr(tiles, "COGReader", FakeReader)
    monkeypatch.setattr(
        tiles, "colorize", lambda values, legend, **_kwargs: np.zeros((4, 2, 2))
    )
    monkeypatch.setattr(tiles, "render_png", lambda _rgba: b"png")

    assert tiles._render_external_tile(
        "et", source, 1, 2, 3, time="2010-01-01"
    ) == b"png"
    assert calls == ["2010-01-01"]


def test_et_tile_route_returns_503_for_missing_precomputed_legend(
    monkeypatch, tmp_path
):
    source = RasterSource(tmp_path / "2010_8day_01_cog.tif", 1)
    monkeypatch.setattr(
        tiles, "resolve_external_raster", lambda *_args: source
    )

    def unavailable(*_args, **_kwargs):
        raise ETLegendUnavailableError("missing test entry")

    monkeypatch.setattr(tiles, "_render_external_tile", unavailable)

    response = client.get(
        "/data/raster-tiles/et/WebMercatorQuad/5/25/12.png",
        params={"time": "2010-01-01"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "ET legend is unavailable for time '2010-01-01'"
    )
```

Add the required `SimpleNamespace`, NumPy, `RasterSource`, and
`ETLegendUnavailableError` imports if not already present.

- [ ] **Step 3: Run route tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest `
  backend/tests/test_layers.py::test_get_et_legend_uses_precomputed_time_entry `
  backend/tests/test_layers.py::test_get_et_legend_returns_503_when_precomputed_entry_is_unavailable `
  backend/tests/test_tiles.py::test_render_et_tile_uses_precomputed_time_legend `
  backend/tests/test_tiles.py::test_et_tile_route_returns_503_for_missing_precomputed_legend `
  -v -p no:cacheprovider
```

Expected: failures because both routes still call
`get_external_dynamic_legend(...)`, `_render_external_tile` has no `time`
parameter, and the exception is not translated to 503.

- [ ] **Step 4: Route layer metadata through the precomputed lookup**

In `backend/routers/layers.py`, replace the dynamic legend import with:

```python
from backend.et_legends import (
    ETLegendUnavailableError,
    get_precomputed_et_legend,
)
```

Keep `resolve_external_raster("et", time)` before legend lookup so a missing
period remains a 404. Wrap only `get_precomputed_et_legend(time)` and translate
`ETLegendUnavailableError` to:

```python
raise HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail=f"ET legend is unavailable for time '{time}'",
) from exc
```

Do not include `exc` text or an absolute path in the public detail.

- [ ] **Step 5: Route tile rendering through the precomputed lookup**

Change:

```python
def _render_external_tile(
    layer_id: str,
    source: RasterSource,
    x: int,
    y: int,
    z: int,
    time: str = "",
) -> bytes:
```

For `layer_id == "et"`, require non-empty `time` and call
`get_precomputed_et_legend(time)`. Other external layers continue to use the
metadata legend.

Pass `time=time` from `external_raster_tile(...)`. Catch
`ETLegendUnavailableError` around rendering and return the same safe 503
detail used by the layer route.

- [ ] **Step 6: Remove runtime dynamic ET raster sampling**

From `backend/external_rasters.py`, remove:

- `_legend_signature(...)`;
- `_build_external_dynamic_legend(...)`;
- `_cached_external_dynamic_legend(...)`;
- `get_external_dynamic_legend(...)`;
- imports used only by those functions (`lru_cache`, NumPy percentile support,
  and `Resampling` if no remaining caller uses it).

Update tests so no module references `get_external_dynamic_legend`. Confirm
the only remaining `rasterio.open(...)` calls in `external_rasters.py` are for
source resolution/discovery, not legend sampling.

- [ ] **Step 7: Run route and external-raster tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest `
  backend/tests/test_layers.py `
  backend/tests/test_tiles.py `
  backend/tests/test_external_rasters.py `
  backend/tests/test_et_legends.py `
  -v -p no:cacheprovider
```

Expected: all selected tests pass; ET legend and tile tests use only the
precomputed time lookup.

- [ ] **Step 8: Confirm no runtime ET dynamic legend symbol remains**

Run:

```powershell
rg -n "get_external_dynamic_legend|_cached_external_dynamic_legend" backend
```

Expected: no matches and exit code 1.

- [ ] **Step 9: Commit route integration**

```powershell
git add -- `
  backend/routers/layers.py `
  backend/routers/tiles.py `
  backend/external_rasters.py `
  backend/tests/test_layers.py `
  backend/tests/test_tiles.py `
  backend/tests/test_external_rasters.py
git commit -m "perf: serve ET legends without raster sampling"
```

---

### Task 7: Full validation, real data generation, and deployment handoff

**Files:**
- Generate: `data/rasters/et_period/*.tif` (local ignored data; do not commit)
- Generate: `data/stats/et_legends.json`
- Verify: all files changed in Tasks 1–6
- Verify: `Dockerfile.backend` copies `data/stats/` into the production image

**Interfaces:**
- Consumes: converter, precomputer, strict runtime, and route integration from Tasks 1–6.
- Produces: 184 validated local ET COGs, a validated 184-entry legend document, benchmark evidence, and exact upload/deployment commands.

- [ ] **Step 1: Run all focused backend tests**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest `
  backend/tests/test_convert_external_to_cog.py `
  backend/tests/test_et_legends.py `
  backend/tests/test_precompute_et_legends.py `
  backend/tests/test_external_rasters.py `
  backend/tests/test_layers.py `
  backend/tests/test_tiles.py `
  backend/tests/test_query.py `
  -v -p no:cacheprovider
```

Expected: exit code 0 with no failures.

- [ ] **Step 2: Run the complete backend suite**

Run:

```powershell
$env:PYTHONPATH='.'
python -m pytest backend/tests -v -p no:cacheprovider
```

Expected: exit code 0 and no failed tests.

- [ ] **Step 3: Run script dry-run against the real annual files**

Run:

```powershell
python scripts/convert_external_to_cog.py `
  --dataset et `
  --src data/rasters/et `
  --dst data/rasters/et_period `
  --dry-run
```

Expected: four valid annual sources, 184 planned period outputs, first output
ending in `2010_8day_01_cog.tif`, and last output ending in
`2013_8day_46_cog.tif`. The command must not write files.

- [ ] **Step 4: Convert one real period and inspect it before the long run**

Run:

```powershell
python scripts/convert_external_to_cog.py `
  --dataset et `
  --src data/rasters/et `
  --dst data/rasters/et_period `
  --workers 1 `
  --limit 1
rio info data/rasters/et_period/2010_8day_01_cog.tif
rio overview --ls data/rasters/et_period/2010_8day_01_cog.tif
rio cogeo validate data/rasters/et_period/2010_8day_01_cog.tif
```

Expected: conversion succeeds; `count=1`, `dtype=uint16`, `nodata=0`,
`interleave=band`, tiled `512×512`, overviews `2,4,8,16,32`, and valid COG.

- [ ] **Step 5: Convert all remaining real ET periods**

Run:

```powershell
python scripts/convert_external_to_cog.py `
  --dataset et `
  --src data/rasters/et `
  --dst data/rasters/et_period `
  --workers 1
```

Expected: the already valid first period is skipped; all remaining period
jobs succeed; no `.tmp.tif` files remain. Do not use `--force` unless a
specific destination fails structural validation.

- [ ] **Step 6: Precompute the real legend document**

Run:

```powershell
$env:PYTHONPATH='.'
python -m backend.precompute_et_legends `
  --root data/rasters/et_period `
  --output data/stats/et_legends.json
```

Expected: 184 sources processed and one validated JSON document atomically
published.

- [ ] **Step 7: Verify complete data/legend set equality and every COG**

Run this read-only verification:

```powershell
@'
import json
from pathlib import Path

from rio_cogeo.cogeo import cog_validate

from backend.et_legends import validate_et_legend_document
from backend.external_rasters import discover_period_sources

root = Path("data/rasters/et_period")
sources = discover_period_sources(root, reject_duplicates=True)
document = json.loads(
    Path("data/stats/et_legends.json").read_text(encoding="utf-8")
)
legends = validate_et_legend_document(document)
assert len(sources) == 184, len(sources)
assert len(legends) == 184, len(legends)
assert set(sources) == set(legends)
for time, source in sources.items():
    valid, errors, _warnings = cog_validate(source.path)
    assert valid, (time, errors)
print("validated 184 ET COGs and 184 matching legends")
'@ | python -
```

Expected: `validated 184 ET COGs and 184 matching legends`.

- [ ] **Step 8: Benchmark the new single-period COG**

Run:

```powershell
@'
from pathlib import Path
from time import perf_counter

from rio_tiler.io import COGReader

path = Path("data/rasters/et_period/2010_8day_01_cog.tif")
times = []
for _ in range(3):
    started = perf_counter()
    with COGReader(str(path)) as reader:
        reader.tile(25, 12, 5, indexes=1)
    times.append(perf_counter() - started)
print("ET single-period tile seconds:", ", ".join(f"{value:.3f}" for value in times))
'@ | python -
```

Record the three values beside the old 0.334–0.376 second baseline. Success
requires a clear reduction; the design intentionally does not impose a fixed
multiplier.

- [ ] **Step 9: Exercise real runtime metadata, query, and tile behavior**

Run the application in-process with an explicit period root; this does not move
or modify the annual sources:

```powershell
@'
import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend import et_legends
from backend.external_rasters import EXTERNAL_RASTERS, ExternalRasterSpec
from backend.main import app

EXTERNAL_RASTERS["et"] = ExternalRasterSpec(
    Path("data/rasters/et_period"),
    "period_files",
    0.1,
    (0,),
)
client = TestClient(app)

times_response = client.get("/api/layers/et/times")
assert times_response.status_code == 200, times_response.text
times = times_response.json()
assert len(times) == 184, len(times)
assert times[0] == "2010-01-01"
assert times[-1] == "2013-12-27"

legend_response = client.get(
    "/api/layers/et/legend", params={"time": "2010-01-01"}
)
assert legend_response.status_code == 200, legend_response.text
assert len(legend_response.json()["legend"]) == 6

point_response = client.get(
    "/api/query/point",
    params={
        "layerId": "et",
        "time": "2010-01-01",
        "lng": 104,
        "lat": 35,
    },
)
assert point_response.status_code == 200, point_response.text
assert point_response.json()["unit"] == "mm/8天"

tile_response = client.get(
    "/data/raster-tiles/et/WebMercatorQuad/5/25/12.png",
    params={"time": "2010-01-01"},
)
assert tile_response.status_code == 200, tile_response.text
assert tile_response.headers["content-type"] == "image/png"
assert tile_response.content.startswith(b"\x89PNG")

missing_response = client.get(
    "/data/raster-tiles/et/WebMercatorQuad/5/25/12.png",
    params={"time": "2014-01-01"},
)
assert missing_response.status_code == 404, missing_response.text

with tempfile.TemporaryDirectory() as directory:
    broken_path = Path(directory) / "et_legends.json"
    document = json.loads(
        Path("data/stats/et_legends.json").read_text(encoding="utf-8")
    )
    del document["legends"]["2010-01-01"]
    broken_path.write_text(json.dumps(document), encoding="utf-8")
    et_legends.ET_LEGEND_CACHE_PATH = broken_path
    unavailable_response = client.get(
        "/api/layers/et/legend", params={"time": "2010-01-01"}
    )
    assert unavailable_response.status_code == 503, unavailable_response.text

print("184 times, legend, point, tile, 404, and 503 checks passed")
'@ | python -
```

Expected:
`184 times, legend, point, tile, 404, and 503 checks passed`.

- [ ] **Step 10: Verify the production image includes the generated legend**

Run:

```powershell
rg -n "COPY data/stats/" Dockerfile.backend
```

Expected: the Dockerfile copies `data/stats/` into `/app/data/stats/`. If
Docker is available, build the backend image and run:

```powershell
docker build -f Dockerfile.backend -t rs-backend:et-period-test .
docker run --rm rs-backend:et-period-test `
  python -c "from pathlib import Path; assert Path('/app/data/stats/et_legends.json').is_file()"
```

Expected: both commands exit 0. If Docker is unavailable, record the image
check as a deployment-host verification item rather than claiming it passed.

- [ ] **Step 11: Inspect the final scoped diff**

Run:

```powershell
git diff --check
git status --short
git diff 64e18d7 -- `
  scripts/convert_external_to_cog.py `
  backend/external_rasters.py `
  backend/et_legends.py `
  backend/precompute_et_legends.py `
  backend/routers/layers.py `
  backend/routers/tiles.py `
  backend/tests/test_convert_external_to_cog.py `
  backend/tests/test_et_legends.py `
  backend/tests/test_precompute_et_legends.py `
  backend/tests/test_external_rasters.py `
  backend/tests/test_layers.py `
  backend/tests/test_tiles.py `
  data/metadata/layers.json `
  data/stats/et_legends.json
```

Expected: only the approved ET conversion, strict runtime, precomputed legend,
tests, metadata, and generated legend changes are present in the scoped diff.

- [ ] **Step 12: Commit the validated real legend artifact**

Do not stage `data/rasters/et_period`; raster data remains ignored and is
uploaded separately. Stage only the small validated JSON:

```powershell
git add -- data/stats/et_legends.json
git commit -m "data: add precomputed ET legends"
```

- [ ] **Step 13: Upload and deploy in the approved order**

On the server, create a new ET directory outside the live path, upload all 184
period COGs, and verify their count before switching the data directory. Then
deploy the code/image containing `et_legends.json`. Do not delete annual files
yet.

After deployment, verify representative 2010/2011/2012/2013 times and inspect
the existing Nginx `X-Tile-Cache` behavior for one ET tile: first request
`MISS`, second request `HIT`.

- [ ] **Step 14: Delete old annual files only after production acceptance**

Resolve and list the exact four old annual paths, verify that no new
`YYYY_8day_PP_cog.tif` path is in the deletion set, retain the local annual
copies for rollback, and then perform the manual server deletion. This is an
operations action requiring explicit target review; no repository script
performs it.
