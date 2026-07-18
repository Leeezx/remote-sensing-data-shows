"""Batch-convert ET and layered soil-moisture rasters to COG.

The source rasters stay untouched. By default, COGs are written under the
project's ``data/rasters`` directory. ET annual files keep all bands; one
band represents one 8-day period.

Examples:
    python scripts/convert_external_to_cog.py --dry-run
    python scripts/convert_external_to_cog.py --dataset sm30
    python scripts/convert_external_to_cog.py --dataset et --workers 2
    python scripts/convert_external_to_cog.py --dataset sm30 --limit 1 \
        --src "F:\\...\\SM30cm预测结果" --dst "E:\\tmp\\sm30_cog"
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(r"F:\全国灌溉用水反演\数据2010-2013")


@dataclass(frozen=True)
class DatasetConfig:
    key: str
    source: Path
    default_destination: Path
    nodata: float | None = None
    overview_resampling: str = "average"


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


def needs_conversion(source: Path, destination: Path, force: bool = False) -> bool:
    """Return whether the destination is missing, stale, or forced."""
    if force or not destination.is_file():
        return True
    return source.stat().st_mtime > destination.stat().st_mtime


def convert_one(
    source: Path,
    destination: Path,
    nodata: float | None,
    overview_resampling: str = "average",
) -> tuple[str, bool, str]:
    """Convert one source to a lossless COG while preserving every band."""
    from rio_cogeo.cogeo import cog_translate
    from rio_cogeo.profiles import cog_profiles

    destination.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(cog_profiles.get(COG_PROFILE))
    profile["blockxsize"] = COG_BLOCKSIZE
    profile["blockysize"] = COG_BLOCKSIZE
    if nodata is not None:
        profile["nodata"] = nodata

    try:
        cog_translate(
            str(source),
            str(destination),
            profile,
            indexes=None,  # Preserve all 46 ET bands; do not reduce to band 1.
            add_mask=True,
            nodata=nodata,
            overview_resampling=overview_resampling,
            quiet=True,
        )
        return source.name, True, ""
    except Exception as exc:  # pragma: no cover - exact GDAL errors vary by host
        if destination.is_file():
            destination.unlink()
        return source.name, False, str(exc)


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
    jobs: list[tuple[Path, Path, float | None, str]] = []

    for config in selected_datasets(args):
        sources = collect_sources(config.source)
        print(f"{config.key}: {len(sources)} source TIFF(s)")
        print(f"  source: {config.source}")
        print(f"  output: {config.default_destination}")
        if not sources:
            print("  WARNING: source directory is missing or empty")
            continue
        if args.dry_run:
            for source in sources[:5]:
                print(f"  {source.name} -> {output_path(source, config.default_destination).name}")
            if len(sources) > 5:
                print(f"  ... and {len(sources) - 5} more")
            continue
        for source in sources:
            destination = output_path(source, config.default_destination)
            if needs_conversion(source, destination, force=args.force):
                jobs.append(
                    (source, destination, config.nodata, config.overview_resampling)
                )

    if args.dry_run:
        return 0
    if args.limit is not None:
        jobs = jobs[:args.limit]
    if not jobs:
        print("No conversion needed.")
        return 0

    total = len(jobs)
    total_size = sum(source.stat().st_size for source, _, _, _ in jobs)
    print(f"Converting {total} file(s), {total_size / 2**30:.2f} GiB")
    print(f"Profile: {COG_PROFILE}, block size: {COG_BLOCKSIZE}, workers: {args.workers}")

    success = 0
    failed = 0
    started = time.time()

    if args.workers == 1:
        results = (
            convert_one(source, destination, nodata, overview_resampling)
            for source, destination, nodata, overview_resampling in jobs
        )
        for index, (name, ok, error) in enumerate(results, 1):
            success += int(ok)
            failed += int(not ok)
            detail = "" if ok else f": {error}"
            print(f"[{index}/{total}] {'OK' if ok else 'FAIL'} {name}{detail}")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(convert_one, source, destination, nodata, overview_resampling): source.name
                for source, destination, nodata, overview_resampling in jobs
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
