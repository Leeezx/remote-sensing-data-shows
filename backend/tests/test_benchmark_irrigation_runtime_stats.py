import subprocess
import sys
from pathlib import Path

from scripts.benchmark_irrigation_runtime_stats import (
    evaluate_budget,
    resident_memory_bytes,
)


def test_evaluate_budget_accepts_target_measurements():
    assert evaluate_budget(
        cold_ms=250,
        hot_ms=75,
        rss_delta_mib=80,
        cold_limit_ms=300,
        hot_limit_ms=100,
        rss_limit_mib=100,
    ) == []


def test_evaluate_budget_reports_every_violation():
    assert evaluate_budget(
        cold_ms=301,
        hot_ms=101,
        rss_delta_mib=101,
        cold_limit_ms=300,
        hot_limit_ms=100,
        rss_limit_mib=100,
    ) == [
        "cold request 301.0 ms exceeds 300.0 ms",
        "hot request 101.0 ms exceeds 100.0 ms",
        "RSS delta 101.0 MiB exceeds 100.0 MiB",
    ]


def test_resident_memory_bytes_reports_current_process_usage():
    assert resident_memory_bytes() > 0


def test_benchmark_cli_can_run_directly_from_project_root():
    project_root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_irrigation_runtime_stats.py",
            "--help",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--rss-limit-mib" in result.stdout
