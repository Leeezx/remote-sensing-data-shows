import json
from pathlib import Path

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


def test_build_chunks_publishes_old_township_under_current_county(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "township_by_county"
    township_source.touch()
    county_source.touch()
    series_path.write_text(json.dumps({
        "township": {"231121100001": {"monthly": [], "annual": []}},
    }), encoding="utf-8")

    county_feature = feature(
        "156231183",
        "嫩江市",
        polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
    )
    township_feature = feature(
        "231121100001",
        "旧嫩江县乡镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )

    def fake_features(path):
        return iter([county_feature] if path == county_source else [township_feature])

    monkeypatch.setattr(chunk_builder, "iter_shapefile_geojson_features", fake_features)

    manifest = chunk_builder.build_chunks(
        township_source,
        county_source,
        series_path,
        output,
        tolerance=0,
        max_bytes=1_000_000,
        max_features=499,
        force=False,
    )

    assert not (output / "231121.geojson").exists()
    chunk = json.loads((output / "231183.geojson").read_text(encoding="utf-8"))
    assert chunk["features"][0]["properties"] == {
        "id": "231121100001",
        "name": "旧嫩江县乡镇",
        "level": "township",
        "parentId": "156231183",
    }
    assert manifest["alignment"] == {
        "direct": 0,
        "spatial": 1,
        "excluded": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "invalidGeometry": 0,
        "missingSeries": 0,
    }


def test_build_chunks_audits_unmatched_and_preserves_existing_output(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "township_by_county"
    township_source.touch()
    county_source.touch()
    series_path.write_text(json.dumps({
        "township": {"231121100001": {}},
    }), encoding="utf-8")
    output.mkdir()
    (output / "sentinel.geojson").write_text("old", encoding="utf-8")

    township = feature(
        "231121100001",
        "无匹配镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )
    monkeypatch.setattr(
        chunk_builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([] if path == county_source else [township]),
    )

    with pytest.raises(ValueError, match="alignment audit"):
        chunk_builder.build_chunks(
            township_source,
            county_source,
            series_path,
            output,
            0,
            1_000_000,
            499,
            force=True,
        )

    assert (output / "sentinel.geojson").read_text(encoding="utf-8") == "old"
    audit = json.loads(
        (tmp_path / "township_by_county.alignment-audit.json").read_text(
            encoding="utf-8",
        ),
    )
    assert audit["issues"][0]["reason"] == "unmatched"


def test_build_chunks_requires_every_output_id_in_township_series(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "out"
    township_source.touch()
    county_source.touch()
    series_path.write_text('{"township": {}}', encoding="utf-8")
    county = feature(
        "156231183",
        "嫩江市",
        polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
    )
    township = feature(
        "231121100001",
        "缺序列镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )
    monkeypatch.setattr(
        chunk_builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([county] if path == county_source else [township]),
    )

    with pytest.raises(ValueError, match="missing township series"):
        chunk_builder.build_chunks(
            township_source,
            county_source,
            series_path,
            output,
            0,
            1_000_000,
            499,
            force=False,
        )

    assert not output.exists()


def test_explicit_exclusion_requires_a_nonempty_reason():
    with pytest.raises(ValueError, match="non-empty reason"):
        chunk_builder.validate_exclusions({"231121100001": ""})

    assert chunk_builder.validate_exclusions({
        "231121100001": "source does not cover this jurisdiction",
    }) == {
        "231121100001": "source does not cover this jurisdiction",
    }


def test_build_chunks_records_a_reviewed_exclusion(monkeypatch, tmp_path):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "out"
    township_source.touch()
    county_source.touch()
    series_path.write_text('{"township": {}}', encoding="utf-8")
    excluded = feature(
        "231121100001",
        "明确排除镇",
        polygon([[[125, 49], [126, 49], [126, 50], [125, 49]]]),
    )
    monkeypatch.setattr(
        chunk_builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([] if path == county_source else [excluded]),
    )

    manifest = chunk_builder.build_chunks(
        township_source,
        county_source,
        series_path,
        output,
        0,
        1_000_000,
        499,
        force=False,
        exclusions={"231121100001": "unsupported source jurisdiction"},
    )

    assert manifest["alignment"]["excluded"] == 1
    assert manifest["excludedTownships"] == {
        "231121100001": "unsupported source jurisdiction",
    }
    assert manifest["featureCount"] == 0


def test_fit_chunk_rejects_payload_that_cannot_meet_the_byte_limit():
    oversized_feature = feature(
        "231121100001",
        "字节上限测试镇",
        polygon([[[0, 0], [10, 0], [10, 10], [0, 0]]]),
    )

    with pytest.raises(ValueError, match="limit is 20"):
        chunk_builder._fit_chunk_to_limit([oversized_feature], 0, 20)


def test_build_chunks_rejects_a_county_above_the_feature_limit(
    monkeypatch,
    tmp_path,
):
    township_source = tmp_path / "township.shp"
    county_source = tmp_path / "county.shp"
    series_path = tmp_path / "series.json"
    output = tmp_path / "out"
    township_source.touch()
    county_source.touch()
    ids = ["231121100001", "231121100002"]
    series_path.write_text(json.dumps({
        "township": {region_id: {} for region_id in ids},
    }), encoding="utf-8")
    county = feature(
        "156231183",
        "嫩江市",
        polygon([[[120, 45], [130, 45], [130, 55], [120, 55], [120, 45]]]),
    )
    townships = [
        feature(
            region_id,
            f"测试镇{index}",
            polygon([[
                [125 + index, 49],
                [125.4 + index, 49],
                [125 + index, 49.4],
                [125 + index, 49],
            ]]),
        )
        for index, region_id in enumerate(ids)
    ]
    monkeypatch.setattr(
        chunk_builder,
        "iter_shapefile_geojson_features",
        lambda path: iter([county] if path == county_source else townships),
    )

    with pytest.raises(ValueError, match="limit is 1"):
        chunk_builder.build_chunks(
            township_source,
            county_source,
            series_path,
            output,
            0,
            1_000_000,
            1,
            force=False,
        )

    assert not output.exists()


def test_publish_staged_directory_restores_old_output_when_swap_fails(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "township_by_county"
    staged = tmp_path / "staged"
    output.mkdir()
    staged.mkdir()
    (output / "old.geojson").write_text("old", encoding="utf-8")
    (staged / "new.geojson").write_text("new", encoding="utf-8")
    real_replace = Path.replace

    def failing_replace(path, target):
        if path == staged:
            raise OSError("simulated staged swap failure")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="simulated staged swap failure"):
        chunk_builder._publish_staged_directory(staged, output)

    assert (output / "old.geojson").read_text(encoding="utf-8") == "old"
    assert not (output / "new.geojson").exists()
