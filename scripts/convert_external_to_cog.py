"""Batch-convert ET and layered soil-moisture rasters to COG.

The source rasters stay untouched. By default, COGs are written under the
project's ``data/rasters`` directory. ET annual files are planned as one COG
per 8-day period.

Examples:
    python scripts/convert_external_to_cog.py --dry-run
    python scripts/convert_external_to_cog.py --dataset sm30
    python scripts/convert_external_to_cog.py --dataset et \
      --src data/rasters/et --dst data/rasters/et_period --workers 1
    python scripts/convert_external_to_cog.py --dataset sm30 --limit 1 \
        --src "F:\\...\\SM30cm预测结果" --dst "E:\\tmp\\sm30_cog"
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
import time
import uuid

import rasterio


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(r"F:\全国灌溉用水反演\数据2010-2013")
ET_PERIODS_PER_YEAR = 46
ET_OVERVIEW_LEVEL = 5


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    source: Path
    default_destination: Path
    nodata: float | None = None
    overview_resampling: str = "average"


@dataclass(frozen=True)
class ConversionJob:
    source: Path
    destination: Path
    nodata: float | None
    overview_resampling: str
    indexes: tuple[int, ...] | None = None
    overview_level: int | None = None


DATASETS = {
    "et": DatasetConfig(
        "et", DATA_ROOT / "ET", PROJECT_ROOT / "data" / "rasters" / "et", 0
    ),
    "sm10": DatasetConfig(
        "sm10", DATA_ROOT / "SM10cm_500m", PROJECT_ROOT / "data" / "rasters" / "sm_10cm", -999
    ),
    "sm30": DatasetConfig(
        "sm30", DATA_ROOT / "SM30cm预测结果", PROJECT_ROOT / "data" / "rasters" / "sm_30cm", -999, "nearest"
    ),
    "sm60": DatasetConfig(
        "sm60", DATA_ROOT / "SM60cm预测结果", PROJECT_ROOT / "data" / "rasters" / "sm_60cm", -999, "nearest"
    ),
    "sm100": DatasetConfig(
        "sm100", DATA_ROOT / "SM100cm预测结果", PROJECT_ROOT / "data" / "rasters" / "sm_100cm", -999, "nearest"
    ),
}

COG_PROFILE = "deflate"
COG_BLOCKSIZE = 512
SUPPORTED_EXTENSIONS = {".tif", ".tiff"}


def collect_sources(source_dir: Path) -> list[Path]:
    """Return source GeoTIFFs in deterministic filename order."""
    if not source_dir.is_dir():
        return []
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def output_path(source: Path, destination: Path) -> Path:
    """Build a COG filename without overwriting the source TIFF."""
    return destination / f"{source.stem}_cog.tif"


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


def validate_conversion_roots(config: DatasetConfig) -> None:
    if (
        config.key == "et"
        and config.source.resolve() == config.default_destination.resolve()
    ):
        raise ValueError(
            "ET source and destination directories must be different"
        )


def needs_conversion(source: Path, destination: Path, force: bool = False) -> bool:
    """Return whether the destination is missing, stale, or forced."""
    if force or not destination.is_file():
        return True
    return source.stat().st_mtime > destination.stat().st_mtime


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


def convert_one(
    source: Path,
    destination: Path,
    nodata: float | None,
    overview_resampling: str = "average",
    indexes: tuple[int, ...] | None = None,
    overview_level: int | None = None,
) -> tuple[str, bool, str]:
    """Convert one source to a validated COG using an atomic replacement."""
    from rio_cogeo.cogeo import cog_validate
    from rio_cogeo.profiles import cog_profiles

    profile = dict(cog_profiles.get(COG_PROFILE))
    profile["blockxsize"] = COG_BLOCKSIZE
    profile["blockysize"] = COG_BLOCKSIZE
    profile["interleave"] = "band"
    if nodata is not None:
        profile["nodata"] = nodata

    temporary = destination.with_name(
        f".{destination.name}.{uuid.uuid4().hex}.tmp.tif"
    )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _translate_cog(
            source,
            temporary,
            profile,
            indexes=indexes,
            nodata=nodata,
            overview_level=overview_level,
            overview_resampling=overview_resampling,
        )
        valid, errors, _warnings = cog_validate(temporary)
        if not valid:
            raise RuntimeError(f"COG validation failed: {errors}")
        with rasterio.open(temporary) as dataset:
            if indexes is not None and len(indexes) == 1 and dataset.count != 1:
                raise RuntimeError(
                    f"Expected one output band; found {dataset.count}"
                )
        os.replace(temporary, destination)
        return source.name, True, ""
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return source.name, False, str(exc)


def run_conversion_job(job: ConversionJob) -> tuple[str, bool, str]:
    return convert_one(
        job.source,
        job.destination,
        job.nodata,
        job.overview_resampling,
        job.indexes,
        job.overview_level,
    )


def destination_is_complete(job: ConversionJob) -> bool:
    from rio_cogeo.cogeo import cog_validate

    if not job.destination.is_file():
        return False
    try:
        valid, _errors, _warnings = cog_validate(job.destination)
        if not valid:
            return False
        with (
            rasterio.open(job.source) as source,
            rasterio.open(job.destination) as destination,
        ):
            if (
                destination.crs != source.crs
                or destination.width != source.width
                or destination.height != source.height
                or not destination.is_tiled
                or any(
                    shape != (COG_BLOCKSIZE, COG_BLOCKSIZE)
                    for shape in destination.block_shapes
                )
            ):
                return False

            expected_count = (
                len(job.indexes) if job.indexes is not None else source.count
            )
            if destination.count != expected_count:
                return False

            if job.indexes is not None and len(job.indexes) == 1:
                return (
                    destination.count == 1
                    and destination.nodata == 0
                    and destination.profile.get("interleave") == "band"
                    and destination.dtypes == ("uint16",)
                    and destination.overviews(1) == [2, 4, 8, 16, 32]
                )
    except (OSError, rasterio.errors.RasterioError):
        return False
    return True


def needs_job_conversion(job: ConversionJob, force: bool = False) -> bool:
    if force or not destination_is_complete(job):
        return True
    return job.source.stat().st_mtime > job.destination.stat().st_mtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert ET and layered soil-moisture GeoTIFFs to COG"
    )
    parser.add_argument(
        "--dataset",
        choices=["all", *DATASETS],
        default="all",
        help="Dataset to convert (default: all)",
    )
    parser.add_argument(
        "--src",
        type=Path,
        help="Override the source directory; only valid for one dataset",
    )
    parser.add_argument(
        "--dst",
        type=Path,
        help="Override the destination directory; only valid for one dataset",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel conversions (default: 1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Convert at most N files, useful for a smoke test",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reconvert even when the destination is newer",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List source files and planned outputs without writing COGs",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if (args.src or args.dst) and args.dataset == "all":
        parser.error("--src/--dst require --dataset to select one dataset")
    if args.src and not args.dst:
        parser.error("--dst is required when --src is provided")
    if args.dst and not args.src:
        parser.error("--src is required when --dst is provided")
    return args


def selected_datasets(args: argparse.Namespace) -> list[DatasetConfig]:
    if args.dataset == "all":
        return list(DATASETS.values())
    config = DATASETS[args.dataset]
    if args.src:
        return [
            DatasetConfig(
                config.key,
                args.src,
                args.dst,
                config.nodata,
                config.overview_resampling,
            )
        ]
    return [config]


def main() -> int:
    args = parse_args()
    jobs: list[ConversionJob] = []

    for config in selected_datasets(args):
        validate_conversion_roots(config)
        sources = collect_sources(config.source)
        print(f"{config.key}: {len(sources)} source TIFF(s)")
        print(f"  source: {config.source}")
        print(f"  output: {config.default_destination}")
        if not sources:
            print("  WARNING: source directory is missing or empty")
            continue
        planned_jobs = build_conversion_jobs(config, sources)
        jobs.extend(
            job
            for job in planned_jobs
            if needs_job_conversion(job, force=args.force)
        )

    if args.limit is not None:
        jobs = jobs[:args.limit]
    if args.dry_run:
        print(f"Planned conversion: {len(jobs)} COG(s)")
        for job in jobs[:10]:
            print(f"  {job.source.name} -> {job.destination.name}")
        if len(jobs) > 10:
            print(f"  ... and {len(jobs) - 10} more")
        return 0
    if not jobs:
        print("No conversion needed.")
        return 0

    total = len(jobs)
    total_size = sum(job.source.stat().st_size for job in jobs)
    print(f"Converting {total} file(s), {total_size / 2**30:.2f} GiB")
    print(f"Profile: {COG_PROFILE}, block size: {COG_BLOCKSIZE}, workers: {args.workers}")

    success = 0
    failed = 0
    started = time.time()

    if args.workers == 1:
        results = (run_conversion_job(job) for job in jobs)
        for index, (name, ok, error) in enumerate(results, 1):
            success += int(ok)
            failed += int(not ok)
            detail = "" if ok else f": {error}"
            print(f"[{index}/{total}] {'OK' if ok else 'FAIL'} {name}{detail}")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(run_conversion_job, job): job.source.name
                for job in jobs
            }
            for index, future in enumerate(as_completed(futures), 1):
                name, ok, error = future.result()
                success += int(ok)
                failed += int(not ok)
                detail = "" if ok else f": {error}"
                print(f"[{index}/{total}] {'OK' if ok else 'FAIL'} {name}{detail}")

    elapsed = time.time() - started
    print(f"Done in {elapsed / 60:.1f} min: {success} succeeded, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
