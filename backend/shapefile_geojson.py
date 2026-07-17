"""Small Shapefile reader for polygon administrative boundaries."""

from pathlib import Path
import struct


def _dbf_encoding(dbf_path: Path) -> str:
    cpg_path = dbf_path.with_suffix(".cpg")
    if cpg_path.is_file():
        text = cpg_path.read_text(encoding="ascii", errors="ignore").strip()
        if text:
            return text
    return "gbk"


def _read_dbf_records(dbf_path: Path) -> list[dict]:
    data = dbf_path.read_bytes()
    if len(data) < 32:
        return []
    record_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    encoding = _dbf_encoding(dbf_path)

    fields = []
    offset = 1
    pos = 32
    while pos < header_length and data[pos] != 0x0D:
        descriptor = data[pos:pos + 32]
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii", errors="ignore")
        length = descriptor[16]
        fields.append((name, offset, length))
        offset += length
        pos += 32

    records = []
    for index in range(record_count):
        start = header_length + index * record_length
        record = data[start:start + record_length]
        if not record or record[0:1] == b"*":
            records.append({})
            continue
        properties = {}
        for name, field_offset, length in fields:
            raw = record[field_offset:field_offset + length].strip(b" \0")
            properties[name] = raw.decode(encoding, errors="ignore").strip(" \0")
        records.append(properties)
    return records


def _shape_records(shp_path: Path):
    """Yield shape records without loading the entire .shp into memory."""
    with shp_path.open("rb") as source:
        source.seek(100)
        while True:
            header = source.read(8)
            if len(header) < 8:
                return
            record_number, content_words = struct.unpack(">2i", header)
            content = source.read(content_words * 2)
            if len(content) < 4:
                continue
            shape_type = struct.unpack("<i", content[:4])[0]
            if shape_type == 0:
                continue
            yield record_number, shape_type, content


def _polygon_geometry(content: bytes) -> dict | None:
    if len(content) < 44:
        return None
    shape_type = struct.unpack("<i", content[:4])[0]
    if shape_type not in (5, 15, 25):
        return None
    num_parts, num_points = struct.unpack("<2i", content[36:44])
    parts_start = 44
    points_start = parts_start + num_parts * 4
    parts = list(struct.unpack(f"<{num_parts}i", content[parts_start:points_start]))
    points = []
    for index in range(num_points):
        start = points_start + index * 16
        x, y = struct.unpack("<2d", content[start:start + 16])
        points.append([x, y])

    rings = []
    for part_index, part_start in enumerate(parts):
        part_end = parts[part_index + 1] if part_index + 1 < len(parts) else len(points)
        ring = points[part_start:part_end]
        if len(ring) >= 4:
            rings.append(ring)
    if not rings:
        return None
    if len(rings) == 1:
        return {"type": "Polygon", "coordinates": [rings[0]]}
    return {
        "type": "MultiPolygon",
        "coordinates": [[[point for point in ring]] for ring in rings],
    }


def iter_shapefile_geojson_features(shp_path: Path):
    """Yield GeoJSON polygon features from a .shp/.dbf pair."""
    dbf_path = shp_path.with_suffix(".dbf")
    records = _read_dbf_records(dbf_path) if dbf_path.is_file() else []
    for record_index, (_record_number, _shape_type, content) in enumerate(
        _shape_records(shp_path)
    ):
        geometry = _polygon_geometry(content)
        if geometry is None:
            continue
        properties = records[record_index] if record_index < len(records) else {}
        region_name = properties.get("name") or properties.get("NAME") or ""
        region_id = properties.get("gb") or properties.get("GB") or str(record_index + 1)
        yield {
            "type": "Feature",
            "properties": {
                **properties,
                "id": region_id,
                "name": region_name or region_id,
            },
            "geometry": geometry,
        }


def read_shapefile_geojson(shp_path: Path) -> dict:
    """Read polygon features from a .shp/.dbf pair into GeoJSON."""
    return {
        "type": "FeatureCollection",
        "features": list(iter_shapefile_geojson_features(shp_path)),
    }
