"""Build compact county-scoped township GeoJSON chunks.

The runtime API serves these files directly and never parses the nationwide
township Shapefile. Run from the repository root:

    python scripts/build_township_chunks.py
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.shapefile_geojson import iter_shapefile_geojson_features
from backend.township_chunks import (
    MAX_TOWNSHIP_CHUNK_BYTES,
    MAX_TOWNSHIP_FEATURES,
    county_code_from_id,
    county_id_from_code,
    township_parent_code,
)


DEFAULT_SOURCE = Path(r"F:\矢量底图\中国_乡镇\乡镇街道\乡镇街道.shp")
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "vectors" / "irrigation" / "township_by_county"
)


Point = tuple[float, float]
Ring = list[list[float]]


def _validated_ring(ring) -> Ring:
    if not isinstance(ring, (list, tuple)) or len(ring) < 4:
        raise ValueError("Polygon ring must contain at least four coordinates")

    normalized: Ring = []
    for coordinate in ring:
        if (
            not isinstance(coordinate, (list, tuple))
            or len(coordinate) < 2
            or isinstance(coordinate[0], bool)
            or isinstance(coordinate[1], bool)
        ):
            raise ValueError("Polygon ring has an invalid coordinate")
        try:
            x = float(coordinate[0])
            y = float(coordinate[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("Polygon ring has a non-numeric coordinate") from exc
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Polygon ring has a non-finite coordinate")
        normalized.append([x, y])

    if normalized[0] != normalized[-1]:
        raise ValueError("Polygon ring is not closed")
    if len({tuple(point) for point in normalized[:-1]}) < 3:
        raise ValueError("Polygon ring has fewer than three distinct vertices")
    if _signed_ring_area(normalized) == 0:
        raise ValueError("Polygon ring has zero signed area")
    return normalized


def geometry_rings(geometry: dict) -> list[Ring]:
    """Return validated polygon rings, including MultiPolygon parts."""
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        rings = list(coordinates)
    elif geometry_type == "MultiPolygon":
        rings = [ring for polygon in coordinates for ring in polygon]
    else:
        raise ValueError(f"Unsupported polygon geometry: {geometry_type}")
    if not rings:
        raise ValueError("Polygon geometry has no rings")
    return [_validated_ring(ring) for ring in rings]


def _point_on_segment(point: Point, start: list[float], end: list[float]) -> bool:
    x, y = point
    x1, y1 = start
    x2, y2 = end
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > 1e-10:
        return False
    return (
        min(x1, x2) - 1e-10 <= x <= max(x1, x2) + 1e-10
        and min(y1, y2) - 1e-10 <= y <= max(y1, y2) + 1e-10
    )


def _point_in_ring(point: Point, ring: Ring) -> bool:
    x, y = point
    inside = False
    for start, end in zip(ring, ring[1:] + ring[:1]):
        if _point_on_segment(point, start, end):
            return True
        x1, y1 = start
        x2, y2 = end
        if (y1 > y) != (y2 > y):
            crossing_x = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if crossing_x > x:
                inside = not inside
    return inside


def point_in_geometry(point: Point, geometry: dict) -> bool:
    """Return whether a point is inside a GeoJSON polygon or multipolygon."""
    inside = False
    for ring in geometry_rings(geometry):
        if _point_in_ring(point, ring):
            inside = not inside
    return inside


def _signed_ring_area(ring: Ring) -> float:
    return 0.5 * sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in zip(ring, ring[1:] + ring[:1])
    )


def _ring_centroid(ring: Ring) -> Point | None:
    cross_sum = 0.0
    x_sum = 0.0
    y_sum = 0.0
    for start, end in zip(ring, ring[1:] + ring[:1]):
        cross = start[0] * end[1] - end[0] * start[1]
        cross_sum += cross
        x_sum += (start[0] + end[0]) * cross
        y_sum += (start[1] + end[1]) * cross
    if abs(cross_sum) < 1e-12:
        return None
    return (x_sum / (3 * cross_sum), y_sum / (3 * cross_sum))


def _scanline_intersections(y: float, rings: list[Ring]) -> list[float]:
    intersections: list[float] = []
    for ring in rings:
        for start, end in zip(ring, ring[1:] + ring[:1]):
            x1, y1 = start
            x2, y2 = end
            if (y1 <= y < y2) or (y2 <= y < y1):
                intersections.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    return sorted(intersections)


def representative_point(geometry: dict) -> Point:
    """Find a deterministic interior point without geometry dependencies."""
    rings = geometry_rings(geometry)
    largest_ring = max(rings, key=lambda ring: abs(_signed_ring_area(ring)))
    centroid = _ring_centroid(largest_ring)
    if centroid is not None and point_in_geometry(centroid, geometry):
        return centroid

    y_values = sorted({point[1] for ring in rings for point in ring})
    if len(y_values) < 2:
        raise ValueError("Polygon geometry has no interior")
    middle_y = (y_values[0] + y_values[-1]) / 2
    scanlines = sorted(
        ((start + end) / 2 for start, end in zip(y_values, y_values[1:])),
        key=lambda value: abs(value - middle_y),
    )
    for y in scanlines:
        xs = _scanline_intersections(y, rings)
        intervals = sorted(
            zip(xs[0::2], xs[1::2]),
            key=lambda pair: pair[1] - pair[0],
            reverse=True,
        )
        for start_x, end_x in intervals:
            candidate = ((start_x + end_x) / 2, y)
            if point_in_geometry(candidate, geometry):
                return candidate
    raise ValueError("Polygon geometry has no valid interior point")


@dataclass(frozen=True)
class CountyBoundary:
    code: str
    county_id: str
    name: str
    geometry: dict
    bbox: tuple[float, float, float, float]


class TownshipAlignmentError(ValueError):
    def __init__(
        self,
        reason: str,
        township_id: str,
        name: str,
        point: Point | None,
        candidates: list[str],
    ):
        super().__init__(f"{reason}: {township_id} {name}")
        self.reason = reason
        self.township_id = township_id
        self.name = name
        self.point = point
        self.candidates = candidates

    def as_dict(self) -> dict:
        return {
            "reason": self.reason,
            "townshipId": self.township_id,
            "name": self.name,
            "point": list(self.point) if self.point is not None else None,
            "candidateCountyCodes": self.candidates,
        }


def _geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    points = [point for ring in geometry_rings(geometry) for point in ring]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


class CountySpatialIndex:
    """One-degree grid index for matching township interiors to counties."""

    GRID_SIZE = 1.0

    def __init__(self, counties: list[CountyBoundary]):
        self.by_code = {county.code: county for county in counties}
        self.cells: dict[tuple[int, int], list[CountyBoundary]] = {}
        for county in counties:
            min_x, min_y, max_x, max_y = county.bbox
            for cell_x in range(math.floor(min_x), math.floor(max_x) + 1):
                for cell_y in range(math.floor(min_y), math.floor(max_y) + 1):
                    self.cells.setdefault((cell_x, cell_y), []).append(county)

    @classmethod
    def from_features(cls, features) -> "CountySpatialIndex":
        counties = []
        for feature in features:
            properties = feature.get("properties", {})
            county_id = str(properties.get("id", ""))
            code = county_code_from_id(county_id)
            geometry = feature.get("geometry", {})
            counties.append(CountyBoundary(
                code=code,
                county_id=county_id_from_code(code),
                name=str(properties.get("name", county_id)),
                geometry=geometry,
                bbox=_geometry_bbox(geometry),
            ))
        return cls(counties)

    def _candidates(self, point: Point) -> list[CountyBoundary]:
        x, y = point
        candidates = self.cells.get((math.floor(x), math.floor(y)), [])
        unique = {county.code: county for county in candidates}
        return [
            county
            for county in unique.values()
            if county.bbox[0] <= x <= county.bbox[2]
            and county.bbox[1] <= y <= county.bbox[3]
        ]

    def match(self, feature: dict) -> tuple[CountyBoundary, str]:
        properties = feature.get("properties", {})
        township_id = str(properties.get("id", ""))
        name = str(properties.get("name", township_id))
        try:
            point = representative_point(feature.get("geometry", {}))
        except (TypeError, ValueError) as exc:
            raise TownshipAlignmentError(
                "invalid_geometry", township_id, name, None, [],
            ) from exc
        matches = [
            county
            for county in self._candidates(point)
            if point_in_geometry(point, county.geometry)
        ]
        if len(matches) == 0:
            raise TownshipAlignmentError("unmatched", township_id, name, point, [])
        if len(matches) > 1:
            raise TownshipAlignmentError(
                "ambiguous",
                township_id,
                name,
                point,
                sorted(county.code for county in matches),
            )
        county = matches[0]
        mode = "direct" if township_parent_code(township_id) == county.code else "spatial"
        return county, mode


def _distance_to_segment_squared(point, start, end) -> float:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    if dx == 0 and dy == 0:
        return (px - sx) ** 2 + (py - sy) ** 2
    ratio = ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)
    ratio = max(0.0, min(1.0, ratio))
    nearest_x = sx + ratio * dx
    nearest_y = sy + ratio * dy
    return (px - nearest_x) ** 2 + (py - nearest_y) ** 2


def _simplify_open_line(points: list[list[float]], tolerance: float) -> list[list[float]]:
    if len(points) <= 2 or tolerance <= 0:
        return points
    threshold = tolerance * tolerance
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        start_index, end_index = stack.pop()
        start = points[start_index]
        end = points[end_index]
        farthest_index = -1
        farthest_distance = threshold
        for index in range(start_index + 1, end_index):
            distance = _distance_to_segment_squared(points[index], start, end)
            if distance > farthest_distance:
                farthest_distance = distance
                farthest_index = index
        if farthest_index >= 0:
            keep.add(farthest_index)
            stack.append((start_index, farthest_index))
            stack.append((farthest_index, end_index))
    return [points[index] for index in sorted(keep)]


def simplify_ring(ring: list[list[float]], tolerance: float) -> list[list[float]]:
    """Simplify a closed ring while retaining a valid four-point minimum."""
    if len(ring) < 5 or tolerance <= 0:
        return ring
    points = ring[:-1] if ring[0] == ring[-1] else ring[:]
    if len(points) < 4:
        return ring
    first = points[0]
    split_index = max(
        range(1, len(points)),
        key=lambda index: math.dist(first, points[index]),
    )
    first_half = _simplify_open_line(points[: split_index + 1], tolerance)
    second_half = _simplify_open_line(points[split_index:] + [first], tolerance)
    simplified = first_half[:-1] + second_half
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return simplified if len(simplified) >= 4 else ring


def simplify_geometry(geometry: dict, tolerance: float) -> dict:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        simplified = [simplify_ring(ring, tolerance) for ring in coordinates]
    elif geometry_type == "MultiPolygon":
        simplified = [
            [simplify_ring(ring, tolerance) for ring in polygon]
            for polygon in coordinates
        ]
    else:
        raise ValueError(f"Unsupported township geometry type: {geometry_type}")
    return {"type": geometry_type, "coordinates": simplified}


class _AppendHandlePool:
    def __init__(self, max_open: int = 64):
        self.max_open = max_open
        self.handles: OrderedDict[Path, object] = OrderedDict()

    def write(self, path: Path, text: str) -> None:
        handle = self.handles.pop(path, None)
        if handle is None:
            if len(self.handles) >= self.max_open:
                _, oldest = self.handles.popitem(last=False)
                oldest.close()
            handle = path.open("a", encoding="utf-8", newline="\n")
        handle.write(text)
        handle.write("\n")
        self.handles[path] = handle

    def close(self) -> None:
        for handle in self.handles.values():
            handle.close()
        self.handles.clear()


def _compact_payload(features: list[dict]) -> bytes:
    return json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _fit_chunk_to_limit(
    features: list[dict],
    tolerance: float,
    max_bytes: int,
) -> tuple[bytes, float]:
    current_tolerance = tolerance
    payload = _compact_payload(features)
    for _attempt in range(8):
        if len(payload) <= max_bytes:
            return payload, current_tolerance
        current_tolerance = max(0.0001, current_tolerance * 2)
        for feature in features:
            feature["geometry"] = simplify_geometry(
                feature["geometry"],
                current_tolerance,
            )
        payload = _compact_payload(features)
    raise ValueError(
        f"Chunk remains {len(payload)} bytes after simplification; limit is {max_bytes}"
    )


def validate_exclusions(exclusions: dict[str, str] | None) -> dict[str, str]:
    """Validate explicit, reviewed township exclusions before a build."""
    result: dict[str, str] = {}
    for township_id, reason in (exclusions or {}).items():
        normalized_id = str(township_id)
        normalized_reason = str(reason).strip()
        township_parent_code(normalized_id)
        if not normalized_reason:
            raise ValueError("Every excluded township id needs a non-empty reason")
        result[normalized_id] = normalized_reason
    return result


def _township_series_ids(series_path: Path) -> set[str]:
    payload = json.loads(series_path.read_text(encoding="utf-8"))
    township = payload.get("township", {})
    if not isinstance(township, dict):
        raise ValueError("Series JSON must contain a township object")
    return {str(region_id) for region_id in township}


def _audit_path(output: Path) -> Path:
    return output.with_name(f"{output.name}.alignment-audit.json")


def _publish_staged_directory(staged: Path, output: Path) -> None:
    """Atomically swap the complete chunk directory, restoring failures."""
    backup = output.with_name(f".{output.name}.backup")
    if backup.exists():
        shutil.rmtree(backup)
    if output.exists():
        output.replace(backup)
    try:
        staged.replace(output)
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        if backup.exists():
            backup.replace(output)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def build_chunks(
    source: Path,
    county_source: Path,
    series_path: Path,
    output: Path,
    tolerance: float,
    max_bytes: int,
    max_features: int,
    force: bool,
    exclusions: dict[str, str] | None = None,
) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"Township Shapefile not found: {source}")
    if not county_source.is_file():
        raise FileNotFoundError(f"County Shapefile not found: {county_source}")
    if not series_path.is_file():
        raise FileNotFoundError(f"Township series JSON not found: {series_path}")
    if output.exists() and not force:
        raise FileExistsError(f"Output already exists; pass --force to rebuild: {output}")

    started = time.perf_counter()
    output.parent.mkdir(parents=True, exist_ok=True)
    county_features = list(iter_shapefile_geojson_features(county_source))
    county_index = CountySpatialIndex.from_features(county_features)
    series_ids = _township_series_ids(series_path)
    excluded = validate_exclusions(exclusions)
    alignment_counts = {
        "direct": 0,
        "spatial": 0,
        "excluded": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "invalidGeometry": 0,
        "missingSeries": 0,
    }
    issues: list[dict] = []
    assigned_counties: dict[str, str] = {}
    output_township_ids: set[str] = set()

    with tempfile.TemporaryDirectory(prefix="township-chunks-", dir=output.parent) as temp:
        temp_root = Path(temp)
        records_root = temp_root / "records"
        chunks_root = temp_root / "chunks"
        records_root.mkdir()
        chunks_root.mkdir()
        pool = _AppendHandlePool()
        counts: dict[str, int] = {}
        try:
            for feature in iter_shapefile_geojson_features(source):
                properties = feature.get("properties", {})
                township_id = str(properties.get("id", ""))
                name = str(properties.get("name", township_id))
                if township_id in excluded:
                    alignment_counts["excluded"] += 1
                    continue
                try:
                    county, mode = county_index.match(feature)
                    previous_code = assigned_counties.get(township_id)
                    if previous_code is not None and previous_code != county.code:
                        raise TownshipAlignmentError(
                            "ambiguous",
                            township_id,
                            name,
                            representative_point(feature["geometry"]),
                            sorted({previous_code, county.code}),
                        )
                except TownshipAlignmentError as exc:
                    issues.append(exc.as_dict())
                    count_key = (
                        "invalidGeometry"
                        if exc.reason == "invalid_geometry"
                        else exc.reason
                    )
                    alignment_counts[count_key] += 1
                    continue

                assigned_counties[township_id] = county.code
                alignment_counts[mode] += 1
                output_township_ids.add(township_id)
                compact_feature = {
                    "type": "Feature",
                    "properties": {
                        "id": township_id,
                        "name": name,
                        "level": "township",
                        "parentId": county.county_id,
                    },
                    "geometry": simplify_geometry(feature["geometry"], tolerance),
                }
                pool.write(
                    records_root / f"{county.code}.ndjson",
                    json.dumps(compact_feature, ensure_ascii=False, separators=(",", ":")),
                )
                counts[county.code] = counts.get(county.code, 0) + 1
        finally:
            pool.close()

        for township_id in sorted(output_township_ids - series_ids):
            alignment_counts["missingSeries"] += 1
            issues.append({
                "reason": "missing_series",
                "townshipId": township_id,
                "name": township_id,
                "point": None,
                "candidateCountyCodes": [assigned_counties[township_id]],
            })

        if issues:
            audit = {
                "status": "failed",
                "source": str(source),
                "countySource": str(county_source),
                "seriesSource": str(series_path),
                "alignment": alignment_counts,
                "issues": issues,
            }
            _audit_path(output).write_text(
                json.dumps(audit, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if alignment_counts["missingSeries"]:
                raise ValueError(
                    "Build blocked by missing township series; see alignment audit",
                )
            raise ValueError("Build blocked by alignment audit")

        manifest_chunks = {}
        for records_path in sorted(records_root.glob("*.ndjson")):
            county_code = records_path.stem
            features = [
                json.loads(line)
                for line in records_path.read_text(encoding="utf-8").splitlines()
                if line
            ]
            if len(features) > max_features:
                raise ValueError(
                    f"County {county_code} has {len(features)} townships; limit is {max_features}"
                )
            payload, applied_tolerance = _fit_chunk_to_limit(
                features,
                tolerance,
                max_bytes,
            )
            chunk_path = chunks_root / f"{county_code}.geojson"
            chunk_path.write_bytes(payload)
            manifest_chunks[county_code] = {
                "countyId": county_id_from_code(county_code),
                "featureCount": len(features),
                "bytes": len(payload),
                "tolerance": applied_tolerance,
            }

        manifest = {
            "source": str(source),
            "sourceMtime": source.stat().st_mtime,
            "countySource": str(county_source),
            "countySourceMtime": county_source.stat().st_mtime,
            "countyFeatureCount": len(county_features),
            "seriesSource": str(series_path),
            "chunkCount": len(manifest_chunks),
            "featureCount": sum(counts.values()),
            "townshipIdCount": len(output_township_ids),
            "alignment": alignment_counts,
            "excludedTownships": excluded,
            "maxChunkBytes": max(
                (item["bytes"] for item in manifest_chunks.values()),
                default=0,
            ),
            "maxChunkFeatures": max(
                (item["featureCount"] for item in manifest_chunks.values()),
                default=0,
            ),
            "elapsedSeconds": round(time.perf_counter() - started, 3),
            "chunks": manifest_chunks,
        }
        (chunks_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        _publish_staged_directory(chunks_root, output)
        audit_path = _audit_path(output)
        if audit_path.exists():
            audit_path.unlink()
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tolerance", type=float, default=0.0005)
    parser.add_argument("--max-bytes", type=int, default=MAX_TOWNSHIP_CHUNK_BYTES)
    parser.add_argument("--max-features", type=int, default=MAX_TOWNSHIP_FEATURES)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = build_chunks(
        args.source.resolve(),
        args.output.resolve(),
        args.tolerance,
        args.max_bytes,
        args.max_features,
        args.force,
    )
    print(json.dumps({key: value for key, value in manifest.items() if key != "chunks"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
