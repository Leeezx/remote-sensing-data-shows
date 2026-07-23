"""Offline construction and atomic publication of ET legend documents."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import logging
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
import rasterio
from rasterio.enums import Resampling

from backend.data_loader import get_layer
from backend.et_legends import build_et_legend, validate_et_legend_document
from backend.external_rasters import RasterSource, discover_period_sources


LOGGER = logging.getLogger(__name__)
_START_YEAR = 2010
_END_YEAR = 2013
_PERIODS_PER_YEAR = 46


def _copy_legend(legend: list[dict]) -> list[dict]:
    return [dict(item) for item in legend]


def _canonical_times() -> list[str]:
    return [
        (date(year, 1, 1) + timedelta(days=8 * period)).isoformat()
        for year in range(_START_YEAR, _END_YEAR + 1)
        for period in range(_PERIODS_PER_YEAR)
    ]


def read_et_sample(
    source: RasterSource,
) -> tuple[np.ndarray, np.ndarray, float | None]:
    """Read raw ET values and masks at no more than 512 pixels per dimension."""
    with rasterio.open(source.path) as dataset:
        height = min(dataset.height, 512)
        width = min(dataset.width, 512)
        values = dataset.read(
            source.band,
            out_shape=(height, width),
            resampling=Resampling.average,
        )
        source_mask = dataset.read_masks(
            source.band,
            out_shape=(height, width),
            resampling=Resampling.nearest,
        )
        nodata = dataset.nodata
    return values, source_mask, nodata


def build_et_legend_document(
    root: Path,
    base_legend: list[dict],
    unit: str,
) -> dict:
    """Build a validated, deterministic document for all 184 ET periods."""
    root = Path(root)
    sources = discover_period_sources(root, reject_duplicates=True)
    if not sources:
        raise ValueError(f"No ET period rasters found under '{root}'")

    canonical_times = _canonical_times()
    canonical_time_set = set(canonical_times)
    unexpected_times = sorted(set(sources) - canonical_time_set)
    if unexpected_times:
        joined = ", ".join(unexpected_times)
        raise ValueError(
            "ET period raster(s) outside the 2010-2013 timeline: "
            f"{joined}"
        )

    base_values = _copy_legend(base_legend)
    legends: dict[str, list[dict]] = {}
    for time in canonical_times:
        source = sources.get(time)
        if source is None:
            LOGGER.warning("Missing ET raster for %s; using base legend", time)
            legends[time] = _copy_legend(base_values)
            continue

        values, source_mask, nodata = read_et_sample(source)
        legend = build_et_legend(
            values,
            base_values,
            unit,
            source_mask=source_mask,
            nodata=nodata,
            value_scale=0.1,
            nodata_values=(0,),
        )
        if legend == base_values:
            LOGGER.warning(
                "ET raster for %s has insufficient distinct data; "
                "using base legend",
                time,
            )
        legends[time] = _copy_legend(legend)

    document = {"version": 1, "legends": legends}
    validate_et_legend_document(document)
    return document


def write_et_legend_document(document: dict, output: Path) -> None:
    """Publish a UTF-8 JSON document by atomically replacing the destination."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n"
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Precompute all ET period legends into one JSON document."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/rasters/et"),
        help="directory containing ET period rasters",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/stats/et_legends.json"),
        help="destination JSON document",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line precomputer, returning a process exit status."""
    args = _parser().parse_args(argv)
    try:
        layer = get_layer("et")
        if not layer:
            raise ValueError("ET layer metadata is missing")
        base_legend = layer.get("legend")
        if not isinstance(base_legend, list) or not base_legend:
            raise ValueError("ET layer metadata legend is missing")

        sources = discover_period_sources(args.root, reject_duplicates=True)
        document = build_et_legend_document(
            args.root,
            base_legend,
            str(layer.get("unit", "")),
        )
        write_et_legend_document(document, args.output)
        print(f"Processed {len(sources)} ET period raster(s)")
        print(f"Wrote ET legend document to {args.output}")
        return 0
    except Exception as exc:
        print(f"ET legend precomputation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(main())
