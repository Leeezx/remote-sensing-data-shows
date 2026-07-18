import json

from backend.cache_io import atomic_write_json


def test_atomic_write_json_replaces_complete_file(tmp_path):
    target = tmp_path / "cache" / "legend.json"
    target.parent.mkdir()
    target.write_text('{"old": true}', encoding="utf-8")

    atomic_write_json(target, {"new": [1, 2, 3]})

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": [1, 2, 3]}
    assert list(target.parent.glob("*.tmp")) == []


def test_legend_cache_write_does_not_modify_read_only_seed(monkeypatch, tmp_path):
    from backend import irrigation_legend

    seed = tmp_path / "source" / "irrigation_legends.json"
    seed.parent.mkdir()
    seed.write_text('{"seed": true}', encoding="utf-8")
    runtime = tmp_path / "cache" / "irrigation_legends.json"
    monkeypatch.setattr(irrigation_legend, "_LEGEND_SEED_PATH", seed)
    monkeypatch.setattr(irrigation_legend, "_LEGEND_CACHE_PATH", runtime)
    irrigation_legend._save_legend_disk_cache({"runtime": True})
    assert json.loads(seed.read_text(encoding="utf-8")) == {"seed": True}
    assert json.loads(runtime.read_text(encoding="utf-8")) == {"runtime": True}
