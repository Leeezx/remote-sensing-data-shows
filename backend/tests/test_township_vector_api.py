import json

from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import irrigation as irrigation_router


client = TestClient(app)


def test_township_vector_returns_coded_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "township_vector_not_found",
        "message": "该县暂无乡镇矢量",
        "countyId": "156231183",
    }


def test_township_vector_keeps_corruption_distinct_from_absence(
    monkeypatch,
    tmp_path,
):
    (tmp_path / "231183.geojson").write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Township vector chunk is unreadable"


def test_township_vector_serves_current_county_code(monkeypatch, tmp_path):
    chunk = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "id": "231121100001",
                "name": "测试乡镇",
                "level": "township",
                "parentId": "156231183",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[125, 49], [126, 49], [126, 50], [125, 49]]],
            },
        }],
    }
    (tmp_path / "231183.geojson").write_text(
        json.dumps(chunk, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 200
    assert response.json() == chunk
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert response.headers["etag"]


def test_township_vector_rejects_a_chunk_above_the_byte_limit(
    monkeypatch,
    tmp_path,
):
    (tmp_path / "231183.geojson").write_text(
        '{"type":"FeatureCollection","features":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(irrigation_router, "TOWNSHIP_CHUNK_ROOT", tmp_path)
    monkeypatch.setattr(irrigation_router, "MAX_TOWNSHIP_CHUNK_BYTES", 10)

    response = client.get(
        "/api/irrigation/vectors/township",
        params={"countyId": "156231183"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Township vector chunk exceeds the configured delivery limits"
    )
