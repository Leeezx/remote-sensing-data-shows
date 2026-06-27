"""Batch convert SSM GeoTIFF files to Cloud-Optimized GeoTIFF (COG) format."""

import subprocess
import sys
from pathlib import Path

SRC_DIR = Path(r"F:\全国灌溉用水反演\数据2010-2013\SSM预测结果")
DST_DIR = Path(__file__).resolve().parent.parent / "data" / "rasters" / "ssm"


def convert_to_cog(src: Path, dst: Path) -> bool:
    """Convert a single GeoTIFF to COG using rio cogeo create."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rio", "cogeo", "create",
        str(src),
        str(dst),
        "--cog-profile", "deflate",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAIL {src.name}: {result.stderr.strip()}")
        return False
    print(f"  OK   {src.name} -> {dst.name}")
    return True


def main():
    tif_files = sorted(SRC_DIR.glob("*.tif"))
    if not tif_files:
        print(f"No .tif files found in {SRC_DIR}")
        sys.exit(1)

    print(f"Found {len(tif_files)} TIF files. Converting to COG...")
    ok = 0
    fail = 0
    for tif in tif_files:
        dst = DST_DIR / f"{tif.stem}_cog.tif"
        if convert_to_cog(tif, dst):
            ok += 1
        else:
            fail += 1

    print(f"\nDone: {ok} succeeded, {fail} failed")


if __name__ == "__main__":
    main()
