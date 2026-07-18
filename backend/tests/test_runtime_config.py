from pathlib import Path

import pytest

from backend import runtime_config


def test_parse_cors_origins_trims_and_discards_empty_values():
    assert runtime_config.parse_cors_origins(
        " http://localhost:5173, ,https://maps.example "
    ) == ("http://localhost:5173", "https://maps.example")


def test_positive_int_env_rejects_zero_and_non_numeric(monkeypatch):
    for value in ("0", "-1", "many"):
        monkeypatch.setenv("MAX_AREA_QUERY_PIXELS", value)
        with pytest.raises(RuntimeError, match="MAX_AREA_QUERY_PIXELS"):
            runtime_config.positive_int_env("MAX_AREA_QUERY_PIXELS", 4_000_000)


def test_runtime_paths_are_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("CACHE_ROOT", str(tmp_path / "cache"))
    assert runtime_config.path_env("CACHE_ROOT", Path("unused")).is_absolute()
