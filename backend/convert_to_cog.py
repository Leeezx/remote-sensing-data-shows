"""Batch-convert irrigation GeoTIFF rasters to Cloud-Optimized GeoTIFF (COG).

Reads annual and 8-day irrigation rasters from their configured source
directories, converts each to a DEFLATE-compressed COG with internal
tiling (512×512) and overviews, and writes them to parallel output
directories.  Already-converted files are skipped so interrupted runs
can resume safely.

Usage:
    python backend/convert_to_cog.py
    python backend/convert_to_cog.py --dry-run          # list files only
    python backend/convert_to_cog.py --workers 4         # parallel conversion
"""

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---- configuration --------------------------------------------------------

ANNUAL_SRC = Path(r"F:\IWU_RS_2025")
ANNUAL_DST = PROJECT_ROOT / "data" / "rasters" / "irrigation_annual"

EIGHTDAY_SRC = Path(
    r"F:\全国灌溉用水反演\数据2010-2013\全作物灌溉用水估计\IWU_calculate3"
)
EIGHTDAY_DST = PROJECT_ROOT / "data" / "rasters" / "irrigation_8day"

COG_PROFILE = "deflate"       # lossless compression (alternatives: raw, lzw, zstd, webp)
COG_BLOCKSIZE = 512           # internal tile size


# ---- helpers --------------------------------------------------------------

def collect_sources(src_dir: Path) -> list[Path]:
    """Return sorted TIFF paths from *src_dir*."""
    if not src_dir.is_dir():
        return []
    paths = sorted(
        p for p in src_dir.iterdir()
        if p.suffix.lower() in (".tif", ".tiff")
    )
    return paths


def needs_conversion(src: Path, dst: Path) -> bool:
    """True when *dst* is missing or older than *src*."""
    if not dst.is_file():
        return True
    return src.stat().st_mtime > dst.stat().st_mtime


def convert_one(src: Path, dst: Path) -> tuple[str, bool, str]:
    """Convert a single raster to COG.  Returns (name, ok, message)."""
    from rio_cogeo.cogeo import cog_translate
    from rio_cogeo.profiles import cog_profiles

    dst.parent.mkdir(parents=True, exist_ok=True)
    profile = cog_profiles.get(COG_PROFILE)
    profile["blockxsize"] = COG_BLOCKSIZE
    profile["blockysize"] = COG_BLOCKSIZE

    try:
        cog_translate(
            str(src),
            str(dst),
            profile,
            indexes=(1,),
            add_mask=True,
            quiet=True,
        )
        return (src.name, True, "")
    except Exception as exc:
        # Remove partial output on failure
        if dst.is_file():
            dst.unlink()
        return (src.name, False, str(exc))


# ---- main -----------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Convert irrigation GeoTIFFs to Cloud-Optimized GeoTIFF"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List files without converting anything",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Number of parallel workers (default: 1)",
    )
    parser.add_argument(
        "--src", type=Path, default=None,
        help="Convert a single directory (overrides defaults)",
    )
    parser.add_argument(
        "--dst", type=Path, default=None,
        help="Output directory (required when --src is given)",
    )
    args = parser.parse_args()

    if args.src:
        if not args.dst:
            print("ERROR: --dst is required when --src is given")
            sys.exit(1)
        jobs = [(args.src, args.dst)]
    else:
        jobs = [
            (ANNUAL_SRC, ANNUAL_DST),
            (EIGHTDAY_SRC, EIGHTDAY_DST),
        ]

    # Collect work -------------------------------------------------------
    work_items: list[tuple[Path, Path]] = []
    for src_dir, dst_dir in jobs:
        sources = collect_sources(src_dir)
        if args.dry_run:
            print(f"\n{'='*60}")
            print(f"Source: {src_dir}")
            print(f"Files:  {len(sources)}")
            for s in sources[:5]:
                print(f"  {s.name}  ({s.stat().st_size/2**20:.0f} MB)")
            if len(sources) > 5:
                print(f"  ... and {len(sources)-5} more")
            continue
        for src in sources:
            dst = dst_dir / src.name
            if needs_conversion(src, dst):
                work_items.append((src, dst))

    if args.dry_run:
        total_files = sum(
            len(collect_sources(sd)) for sd, _ in jobs
        )
        print(f"\nTotal: {total_files} files")
        return

    if not work_items:
        print("All files are already converted — nothing to do.")
        return

    total = len(work_items)
    total_size = sum(s.stat().st_size for s, _ in work_items)
    print(f"Converting {total} files ({total_size/2**30:.1f} GB total)")
    print(f"Workers: {args.workers}")
    print(f"Profile: {COG_PROFILE}, block size: {COG_BLOCKSIZE}")
    print()

    ok = 0
    fail = 0
    t_start = time.time()

    if args.workers > 1:
        # Parallel conversion --------------------------------------------
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(convert_one, src, dst): (i, src.name)
                for i, (src, dst) in enumerate(work_items, 1)
            }
            for future in as_completed(futures):
                i, name = futures[future]
                fname, success, error = future.result()
                if success:
                    ok += 1
                    elapsed = time.time() - t_start
                    rate = ok / max(elapsed, 0.1)
                    remaining = (total - i) / max(rate, 0.01)
                    print(
                        f"[{i:4d}/{total}] OK  {fname}  "
                        f"({ok}/{total} done, ~{remaining:.0f}s left)"
                    )
                else:
                    fail += 1
                    print(f"[{i:4d}/{total}] FAIL {fname}: {error}")
    else:
        # Sequential conversion ------------------------------------------
        for i, (src, dst) in enumerate(work_items, 1):
            fname, success, error = convert_one(src, dst)
            elapsed = time.time() - t_start
            rate = i / max(elapsed, 0.1)
            remaining = (total - i) / max(rate, 0.01)
            status = "OK" if success else "FAIL"
            detail = "" if success else f": {error}"
            print(
                f"[{i:4d}/{total}] {status} {fname}  "
                f"({elapsed:.0f}s elapsed, ~{remaining:.0f}s left){detail}"
            )
            if success:
                ok += 1
            else:
                fail += 1

    total_time = time.time() - t_start
    print()
    print(f"Done in {total_time:.0f}s ({total_time/60:.1f} min)")
    print(f"  OK: {ok}, FAIL: {fail}")
    print(f"  Annual output:  {ANNUAL_DST}")
    print(f"  8-day output:   {EIGHTDAY_DST}")


if __name__ == "__main__":
    main()
