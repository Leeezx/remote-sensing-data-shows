"""Tests for SSM 8-day data loading."""
import json
import tempfile
from pathlib import Path


def test_get_layer_times_8day_resolution():
    """get_layer_times with resolution='8day' should load 8-day times file."""
    import backend.data_loader as dl

    original_root = dl.PROJECT_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        dl.PROJECT_ROOT = Path(tmp)

        # Create data directory structure
        (Path(tmp) / "data" / "series").mkdir(parents=True)
        (Path(tmp) / "data" / "metadata").mkdir(parents=True)

        # Write test layers.json
        with open(Path(tmp) / "data" / "metadata" / "layers.json", "w") as f:
            json.dump([{
                "id": "ssm", "name": "SSM", "type": "soil", "unit": "m³/m³",
                "range": {"min": 0, "max": 1},
                "timeRange": {"start": "2010-01", "end": "2010-12", "step": "month"},
                "tileTemplate": "data/tiles/ssm/{time}/{z}/{x}/{y}.png",
                "legend": [{"color": "#ff0000", "label": "dry"}]
            }], f)

        # Write test 8-day times
        times = ["2010-01-01", "2010-01-09", "2010-01-17"]
        with open(Path(tmp) / "data" / "series" / "ssm_8day_times.json", "w") as f:
            json.dump(times, f)

        # Test 8-day resolution
        result = dl.get_layer_times("ssm", resolution="8day")
        assert result == times

        # Clean up
        dl.PROJECT_ROOT = original_root


def test_get_series_8day_resolution():
    """get_series with resolution='8day' should load 8-day series file."""
    import backend.data_loader as dl

    original_root = dl.PROJECT_ROOT
    with tempfile.TemporaryDirectory() as tmp:
        dl.PROJECT_ROOT = Path(tmp)
        (Path(tmp) / "data" / "series").mkdir(parents=True)
        (Path(tmp) / "data" / "metadata").mkdir(parents=True)

        with open(Path(tmp) / "data" / "metadata" / "layers.json", "w") as f:
            json.dump([{
                "id": "ssm", "name": "SSM", "type": "soil", "unit": "m³/m³",
                "range": {"min": 0, "max": 1},
                "timeRange": {"start": "2010-01", "end": "2010-12", "step": "month"},
                "tileTemplate": "data/tiles/ssm/{time}/{z}/{x}/{y}.png",
                "legend": [{"color": "#ff0000", "label": "dry"}]
            }], f)

        series = [
            {"time": "2010-01-01", "value": 0.15},
            {"time": "2010-01-09", "value": 0.18},
            {"time": "2010-01-17", "value": 0.22},
        ]
        with open(Path(tmp) / "data" / "series" / "ssm_8day_series.json", "w") as f:
            json.dump(series, f)

        result = dl.get_series("ssm", resolution="8day")
        assert result == series

        dl.PROJECT_ROOT = original_root
