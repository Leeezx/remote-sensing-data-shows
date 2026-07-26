"""Validate and spatially assign reclamation-potential source rows."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from openpyxl import load_workbook

from scripts.build_township_chunks import point_in_geometry


EXPECTED_COLUMNS = [
    'longitude', 'latitude',
    'EV', 'optimal_irr', 'optimal_npp', 'optimal_soc',
    'EV.1', 'irr', 'npp', 'soc',
]
NODATA = -999.0


@dataclass(frozen=True)
class ScenarioMetrics:
    reclamation_value: float
    water_consumption: float
    yield_value: float
    soil_carbon_value: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (
            self.reclamation_value,
            self.water_consumption,
            self.yield_value,
            self.soil_carbon_value,
        )


@dataclass(frozen=True)
class SourcePoint:
    longitude: float
    latitude: float
    current: ScenarioMetrics
    future: ScenarioMetrics


@dataclass(frozen=True)
class DemoRegion:
    region_id: str
    name: str
    feature: dict


@dataclass(frozen=True)
class RegionAssignment:
    by_region: dict[str, list[SourcePoint]]
    unassigned_indexes: list[int]
    overlapping_indexes: list[int]


def _number(value, *, row_number: int, column: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f'row {row_number}: {column} must be a finite number')
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'row {row_number}: {column} must be a finite number') from exc
    if not math.isfinite(result):
        raise ValueError(f'row {row_number}: {column} must be a finite number')
    return result


def _scenario(values: tuple[float, float, float, float], *, row_number: int, name: str) -> ScenarioMetrics:
    nodata_values = [value == NODATA for value in values]
    if any(nodata_values) and not all(nodata_values):
        raise ValueError(f'row {row_number}: {name} has mixed -999 values')
    return ScenarioMetrics(*values)


def read_workbook_points(path: str | Path) -> list[SourcePoint]:
    """Read a strictly validated reclamation workbook into source points."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if 'pixel_values' not in workbook.sheetnames:
            raise ValueError('row 1: workbook must contain a pixel_values sheet')
        sheet = workbook['pixel_values']
        header = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        if list(header) != EXPECTED_COLUMNS:
            raise ValueError('row 1: pixel_values header must exactly match EXPECTED_COLUMNS')

        points: list[SourcePoint] = []
        coordinates: set[tuple[float, float]] = set()
        for row_number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if len(row) != len(EXPECTED_COLUMNS):
                raise ValueError(f'row {row_number}: expected {len(EXPECTED_COLUMNS)} columns')
            values = tuple(
                _number(value, row_number=row_number, column=column)
                for column, value in zip(EXPECTED_COLUMNS, row)
            )
            longitude, latitude = values[:2]
            if not -180 <= longitude <= 180:
                raise ValueError(f'row {row_number}: longitude must be in [-180, 180]')
            if not -90 <= latitude <= 90:
                raise ValueError(f'row {row_number}: latitude must be in [-90, 90]')
            coordinate = (longitude, latitude)
            if coordinate in coordinates:
                raise ValueError(f'row {row_number}: duplicate coordinate pair')
            coordinates.add(coordinate)
            points.append(SourcePoint(
                longitude=longitude,
                latitude=latitude,
                current=_scenario(values[2:6], row_number=row_number, name='current'),
                future=_scenario(values[6:10], row_number=row_number, name='future'),
            ))
        return points
    finally:
        workbook.close()


def normalize_region_features(features) -> list[DemoRegion]:
    """Normalize WRRCD/WRRNM GeoJSON properties for deterministic assignment."""
    regions: list[DemoRegion] = []
    region_ids: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ValueError(f'region {index}: feature must be an object')
        properties = feature.get('properties')
        if not isinstance(properties, dict):
            raise ValueError(f'region {index}: properties must be an object')
        region_id = str(properties.get('WRRCD', '')).strip()
        name = str(properties.get('WRRNM', '')).strip()
        if not region_id:
            raise ValueError(f'region {index}: WRRCD must be non-empty')
        if not name:
            raise ValueError(f'region {index}: WRRNM must be non-empty')
        if region_id in region_ids:
            raise ValueError(f'region {index}: duplicate WRRCD {region_id}')
        geometry = feature.get('geometry')
        if not isinstance(geometry, dict):
            raise ValueError(f'region {index}: geometry must be an object')
        region_ids.add(region_id)
        normalized_feature = {
            **feature,
            'properties': {**properties, 'id': region_id, 'name': name},
        }
        regions.append(DemoRegion(region_id, name, normalized_feature))
    return regions


def assign_points(points: list[SourcePoint], regions: list[DemoRegion]) -> RegionAssignment:
    """Assign point centers to every matching region and retain audit indexes."""
    by_region = {region.region_id: [] for region in regions}
    unassigned_indexes: list[int] = []
    overlapping_indexes: list[int] = []
    for index, point in enumerate(points):
        matches = [
            region for region in regions
            if point_in_geometry((point.longitude, point.latitude), region.feature['geometry'])
        ]
        for region in matches:
            by_region[region.region_id].append(point)
        if not matches:
            unassigned_indexes.append(index)
        elif len(matches) > 1:
            overlapping_indexes.append(index)
    return RegionAssignment(by_region, unassigned_indexes, overlapping_indexes)
