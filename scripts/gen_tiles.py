#!/usr/bin/env python3
"""Generate tiles for all SSM monthly composites (run from project root)."""
import subprocess
from pathlib import Path

GDALWARP = r"C:\ProgramData\miniconda3\Library\bin\gdalwarp.exe"
GDALDEM = r"C:\ProgramData\miniconda3\Library\bin\gdaldem.exe"
GDAL2TILES = r"C:\ProgramData\miniconda3\envs\irrigation_water\python.exe"

TEMP = Path("temp_ssm")
TILES = Path("data/tiles/ssm")
TILES.mkdir(parents=True, exist_ok=True)

RAMP = "0.09 213 62 79 255\n0.15 252 141 89 255\n0.22 254 224 139 255\n0.28 153 213 148 255\n0.35 50 136 189 255\n0.40 1 108 89 255\nnv 0 0 0 0\n"

composites = sorted(TEMP.glob("ssm_????-??.tif"))
print(f"Found {len(composites)} monthly composites")

for i, comp in enumerate(composites):
    ym = comp.stem.replace("ssm_", "")
    tile_dir = TILES / ym
    tile_dir.mkdir(parents=True, exist_ok=True)

    warped = TEMP / f"{comp.stem}_3857.tif"
    colored = TEMP / f"{comp.stem}_rgba.tif"
    ramp_f = TEMP / f"{comp.stem}_ramp.txt"

    print(f"[{i+1}/{len(composites)}] {ym}...", end=" ", flush=True)
    ramp_f.write_text(RAMP)

    subprocess.run([GDALWARP, "-t_srs", "EPSG:3857", "-r", "average",
        "-srcnodata", "-9999", "-dstnodata", "-9999",
        "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=2", "-co", "TILED=YES",
        "-tr", "500", "500", str(comp), str(warped)],
        capture_output=True, timeout=300)

    subprocess.run([GDALDEM, "color-relief", "-alpha",
        "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=2", "-co", "TILED=YES",
        str(warped), str(ramp_f), str(colored)],
        capture_output=True, timeout=120)

    subprocess.run([GDAL2TILES, "-m", "osgeo_utils.gdal2tiles",
        "--xyz", "--zoom=0-8", "--processes=4", "--resampling=average",
        str(colored), str(tile_dir)],
        capture_output=True, timeout=600)

    n = len(list(tile_dir.rglob("*.png")))
    print(f"OK ({n} tiles)")

    for tmp in [warped, colored, ramp_f]:
        if tmp.exists():
            tmp.unlink()

print("Done!")
