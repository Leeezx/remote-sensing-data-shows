import pytest

import backend.shapefile_geojson as shapefile_geojson
import scripts.build_township_chunks as chunk_builder
from backend.township_chunks import (
    county_code_from_id,
    county_id_from_code,
    township_parent_code,
)
from scripts.build_township_chunks import (
    CountySpatialIndex,
    TownshipAlignmentError,
    point_in_geometry,
    representative_point,
    simplify_ring,
)


def polygon(rings):
    return {"type": "Polygon", "coordinates": rings}


def feature(region_id, name, geometry):
    return {
        "type": "Feature",
        "properties": {"id": region_id, "name": name},
        "geometry": geometry,
    }


def test_county_and_township_codes_map_to_the_same_chunk():
    assert county_code_from_id("156511011") == "511011"
    assert county_code_from_id("511011") == "511011"
    assert county_id_from_code("511011") == "156511011"
    assert township_parent_code("511011111000") == "511011"


def test_simplify_ring_preserves_closure_and_valid_minimum():
    ring = [
        [0.0, 0.0],
        [0.2, 0.01],
        [0.4, 0.0],
        [1.0, 0.0],
        [1.0, 1.0],
        [0.0, 1.0],
        [0.0, 0.0],
    ]

    simplified = simplify_ring(ring, 0.05)

    assert len(simplified) < len(ring)
    assert len(simplified) >= 4
    assert simplified[0] == simplified[-1]


def test_point_in_geometry_respects_a_hole():
    geometry = polygon([
        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
        [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
    ])

    assert point_in_geometry((2, 2), geometry) is True
    assert point_in_geometry((0, 0), geometry) is True
    assert point_in_geometry((5, 5), geometry) is False
    assert point_in_geometry((4, 5), geometry) is False


def test_representative_point_stays_inside_a_concave_polygon_with_a_hole():
    geometry = polygon([
        [[0, 0], [8, 0], [8, 2], [2, 2], [2, 8], [0, 8], [0, 0]],
        [[0.5, 0.5], [1.5, 0.5], [1.5, 1.5], [0.5, 1.5], [0.5, 0.5]],
    ])

    point = representative_point(geometry)

    assert point_in_geometry(point, geometry) is True


def test_representative_point_handles_multipolygon_parts():
    geometry = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 0]]],
            [[[10, 10], [14, 10], [14, 14], [10, 10]]],
        ],
    }

    point = representative_point(geometry)

    assert point_in_geometry(point, geometry) is True


def test_county_index_reports_direct_and_spatial_matches():
    counties = [
        feature(
            "156231183",
            "嫩江市",
            polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
        ),
        feature(
            "156231124",
            "孙吴县",
            polygon([[[130, 45], [140, 45], [140, 55], [130, 55], [130, 45]]]),
        ),
    ]
    index = CountySpatialIndex.from_features(counties)

    direct, direct_mode = index.match(feature(
        "231124100001",
        "直接匹配镇",
        polygon([[[131, 46], [132, 46], [132, 47], [131, 46]]]),
    ))
    remapped, remapped_mode = index.match(feature(
        "231121100001",
        "旧嫩江县乡镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    ))

    assert (direct.code, direct_mode) == ("231124", "direct")
    assert (remapped.code, remapped_mode) == ("231183", "spatial")


def test_county_index_fails_for_unmatched_or_multiple_counties():
    duplicate_geometry = polygon([
        [[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]],
    ])
    index = CountySpatialIndex.from_features([
        feature("156231183", "嫩江市", duplicate_geometry),
        feature("156999999", "重叠测试县", duplicate_geometry),
    ])

    with pytest.raises(TownshipAlignmentError, match="ambiguous"):
        index.match(feature(
            "231121100001",
            "歧义镇",
            polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
        ))

    empty_index = CountySpatialIndex.from_features([])
    with pytest.raises(TownshipAlignmentError, match="unmatched"):
        empty_index.match(feature(
            "231121100002",
            "无匹配镇",
            polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
        ))

    with pytest.raises(TownshipAlignmentError, match="invalid_geometry"):
        index.match({
            "type": "Feature",
            "properties": {"id": "231121100003", "name": "坏几何镇"},
            "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        })


@pytest.mark.parametrize("ring", [
    [[1, 1], [2, 2], [3, 3], [1, 1]],
    [[1, 1], [2, 1], [2, 2], [1, 2]],
    [[1, 1], [2, 1], [1, 1], [1, 1]],
    [[1, 1], [float("inf"), 1], [1, 2], [1, 1]],
])
def test_county_index_rejects_invalid_exterior_rings(ring):
    index = CountySpatialIndex.from_features([
        feature(
            "156231183",
            "嫩江市",
            polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
        ),
    ])

    with pytest.raises(TownshipAlignmentError) as error:
        index.match(feature("231121100004", "退化镇", polygon([ring])))

    assert error.value.reason == "invalid_geometry"


def test_builder_requires_the_committed_streaming_shapefile_reader():
    streaming_reader = getattr(shapefile_geojson, "iter_shapefile_geojson_features", None)

    assert streaming_reader is not None
    assert chunk_builder.iter_shapefile_geojson_features is streaming_reader
