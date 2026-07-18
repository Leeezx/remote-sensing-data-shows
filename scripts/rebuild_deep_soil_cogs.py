"""Rebuild deployable COGs for the 30, 60, and 100 cm soil-moisture layers.

This is an offline data-preparation script.  It intentionally excludes ET and
10 cm soil moisture, and always overwrites the affected COGs so their stale
overview pyramids are replaced with NoData-aware versions.

Examples:
    python scripts/rebuild_deep_soil_cogs.py --dry-run
    python scripts/rebuild_deep_soil_cogs.py --workers 2
    python scripts/rebuild_deep_soil_cogs.py --limit 1
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import sys
import time

from convert_external_to_cog import DATASETS, collect_sources, convert_one, output_path


DEEP_SOIL_DATASETS = ("sm30", "sm60", "sm100")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild NoData-aware COGs for 30/60/100 cm soil moisture"
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
        help="Convert at most N files across all three depths",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned overwrites without changing any files",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    return args


def build_jobs() -> list[tuple[Path, Path, float | None, str]]:
    """Collect every deep-soil source and its project-local COG destination."""
    jobs = []
    for key in DEEP_SOIL_DATASETS:
        config = DATASETS[key]
        sources = collect_sources(config.source)
        print(f"{key}: {len(sources)} source TIFF(s)")
        print(f"  source: {config.source}")
        print(f"  output: {config.default_destination}")
        for source in sources:
            jobs.append(
                (
                    source,
                    output_path(source, config.default_destination),
                    config.nodata,
                    config.overview_resampling,
                )
            )
    return jobs


def main() -> int:
    args = parse_args()
    jobs = build_jobs()
    if args.limit is not None:
        jobs = jobs[:args.limit]

    if args.dry_run:
        print(f"Planned overwrite: {len(jobs)} COG(s)")
        for source, destination, *_ in jobs[:10]:
            print(f"  {source.name} -> {destination}")
        if len(jobs) > 10:
            print(f"  ... and {len(jobs) - 10} more")
        return 0

    total_size = sum(source.stat().st_size for source, *_ in jobs)
    print(f"Rebuilding {len(jobs)} COG(s), {total_size / 2**30:.2f} GiB")
    print(f"Workers: {args.workers}; existing outputs will be overwritten.")
    started = time.time()

    if args.workers == 1:
        results = (convert_one(*job) for job in jobs)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(convert_one, *job) for job in jobs]
            results = (future.result() for future in as_completed(futures))

    failed = 0
    for index, (name, ok, error) in enumerate(results, 1):
        failed += int(not ok)
        detail = "" if ok else f": {error}"
        print(f"[{index}/{len(jobs)}] {'OK' if ok else 'FAIL'} {name}{detail}")

    print(f"Finished in {(time.time() - started) / 60:.1f} min; failures: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
