from openpyxl import Workbook, load_workbook
import pytest

from scripts.build_reclamation_data import (
    EXPECTED_COLUMNS,
    ScenarioMetrics,
    SourcePoint,
    assign_points,
    normalize_region_features,
    read_workbook_points,
)


def write_workbook(path, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'pixel_values'
    sheet.append(EXPECTED_COLUMNS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def make_point(longitude, latitude):
    metrics = ScenarioMetrics(1.0, 2.0, 3.0, 4.0)
    return SourcePoint(longitude, latitude, metrics, metrics)


def test_read_workbook_maps_both_scenarios_and_rejects_mixed_nodata(tmp_path):
    source = tmp_path / 'values.xlsx'
    write_workbook(source, [[105.0, 38.0, 1, 2, 3, 4, -999, -999, -999, -999]])

    points = read_workbook_points(source)

    assert points[0].current.as_tuple() == (1.0, 2.0, 3.0, 4.0)
    assert points[0].future.as_tuple() == (-999.0, -999.0, -999.0, -999.0)

    write_workbook(source, [[105.0, 38.0, 1, -999, 3, 4, 5, 6, 7, 8]])
    with pytest.raises(ValueError, match='row 2.*mixed -999'):
        read_workbook_points(source)


def test_read_workbook_rejects_extra_sheets(tmp_path):
    source = tmp_path / 'values.xlsx'
    write_workbook(source, [])
    workbook = load_workbook(source)
    workbook.create_sheet('notes')
    workbook.save(source)

    with pytest.raises(ValueError, match='exactly one pixel_values sheet'):
        read_workbook_points(source)


def test_normalize_region_features_rejects_duplicate_or_missing_identifiers():
    feature = {
        'type': 'Feature',
        'properties': {'WRRCD': 'A', 'WRRNM': '区域A'},
        'geometry': {'type': 'Polygon', 'coordinates': []},
    }

    duplicate_name = {**feature, 'properties': {'WRRCD': 'B', 'WRRNM': '区域A'}}
    with pytest.raises(ValueError, match='duplicate WRRNM 区域A'):
        normalize_region_features([feature, duplicate_name])

    duplicate_id = {**feature, 'properties': {'WRRCD': 'A', 'WRRNM': '区域B'}}
    with pytest.raises(ValueError, match='duplicate WRRCD A'):
        normalize_region_features([feature, duplicate_id])

    null_id = {**feature, 'properties': {'WRRCD': None, 'WRRNM': '区域A'}}
    with pytest.raises(ValueError, match='WRRCD must be non-empty'):
        normalize_region_features([null_id])

    null_name = {**feature, 'properties': {'WRRCD': 'A', 'WRRNM': None}}
    with pytest.raises(ValueError, match='WRRNM must be non-empty'):
        normalize_region_features([null_name])


def test_assign_points_uses_polygon_centers_and_audits_outside_points():
    regions = normalize_region_features([
        {
            'type': 'Feature',
            'properties': {'WRRCD': 'A', 'WRRNM': '区域A'},
            'geometry': {
                'type': 'Polygon',
                'coordinates': [[[100, 30], [102, 30], [102, 32], [100, 32], [100, 30]]],
            },
        },
    ])
    points = [
        make_point(101.0, 31.0),
        make_point(110.0, 40.0),
    ]

    result = assign_points(points, regions)

    assert [point.longitude for point in result.by_region['A']] == [101.0]
    assert result.unassigned_indexes == [1]
    assert result.overlapping_indexes == []
