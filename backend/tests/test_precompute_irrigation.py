from backend.precompute_irrigation import build_region_catalog


def test_build_region_catalog_preserves_both_levels_and_parent_ids():
    series_data = {
        "unit": "万m³",
        "county": {
            "county_b": {"name": "乙县", "annual": [], "monthly": []},
            "county_a": {"name": "甲县", "annual": [], "monthly": []},
        },
        "township": {
            "township_a2": {"name": "乙镇", "annual": [], "monthly": []},
            "township_a1": {"name": "甲镇", "annual": [], "monthly": []},
        },
    }
    previous = [
        {
            "id": "township_a1",
            "name": "旧名称",
            "level": "township",
            "parentId": "county_a",
        }
    ]

    assert build_region_catalog(series_data, previous) == [
        {"id": "county_a", "name": "甲县", "level": "county", "parentId": None},
        {"id": "county_b", "name": "乙县", "level": "county", "parentId": None},
        {
            "id": "township_a1",
            "name": "甲镇",
            "level": "township",
            "parentId": "county_a",
        },
        {
            "id": "township_a2",
            "name": "乙镇",
            "level": "township",
            "parentId": None,
        },
    ]


def test_build_region_catalog_ignores_unknown_sections_and_invalid_entries():
    series_data = {
        "unit": "万m³",
        "county": {"county_a": {"name": "甲县"}, "broken": "not-an-object"},
        "township": {},
        "province": {"province_a": {"name": "甲省"}},
    }

    assert build_region_catalog(series_data) == [
        {"id": "county_a", "name": "甲县", "level": "county", "parentId": None}
    ]
