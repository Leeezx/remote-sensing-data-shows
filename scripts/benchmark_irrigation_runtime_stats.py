"""Benchmark irrigation runtime statistics against approved budgets."""

from __future__ import annotations

import ctypes
import json
import os
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def evaluate_budget(
    *,
    cold_ms: float,
    hot_ms: float,
    rss_delta_mib: float,
    cold_limit_ms: float,
    hot_limit_ms: float,
    rss_limit_mib: float,
) -> list[str]:
    """Return human-readable budget violations."""
    failures = []
    if cold_ms > cold_limit_ms:
        failures.append(
            f"cold request {cold_ms:.1f} ms exceeds "
            f"{cold_limit_ms:.1f} ms"
        )
    if hot_ms > hot_limit_ms:
        failures.append(
            f"hot request {hot_ms:.1f} ms exceeds {hot_limit_ms:.1f} ms"
        )
    if rss_delta_mib > rss_limit_mib:
        failures.append(
            f"RSS delta {rss_delta_mib:.1f} MiB exceeds "
            f"{rss_limit_mib:.1f} MiB"
        )
    return failures


def _windows_resident_memory_bytes() -> int:
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    success = psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(),
        ctypes.byref(counters),
        counters.cb,
    )
    if not success:
        error_code = ctypes.get_last_error()
        raise OSError(
            error_code,
            "GetProcessMemoryInfo failed",
        )
    return int(counters.WorkingSetSize)


def resident_memory_bytes() -> int:
    """Return current resident memory on Windows or Linux."""
    if sys.platform == "win32":
        return _windows_resident_memory_bytes()
    if sys.platform.startswith("linux"):
        fields = Path("/proc/self/statm").read_text(
            encoding="ascii"
        ).split()
        return int(fields[1]) * int(os.sysconf("SC_PAGE_SIZE"))
    raise RuntimeError(f"RSS measurement is unsupported on {sys.platform}")


def run_benchmark(runtime_root: Path, hot_runs: int) -> dict[str, float]:
    """Measure one cold request and the median of repeated hot requests."""
    from fastapi.testclient import TestClient

    from backend import irrigation_runtime_stats
    from backend.main import app

    irrigation_runtime_stats.IRRIGATION_RUNTIME_STATS_ROOT = runtime_root
    irrigation_runtime_stats.clear_runtime_stats_caches()
    path = "/api/irrigation/regions/averages"
    params = {"level": "county"}

    with TestClient(app) as client:
        rss_before = resident_memory_bytes()
        started = time.perf_counter()
        response = client.get(path, params=params)
        cold_ms = (time.perf_counter() - started) * 1000
        response.raise_for_status()
        rss_after = resident_memory_bytes()

        hot_measurements = []
        for _ in range(hot_runs):
            started = time.perf_counter()
            response = client.get(path, params=params)
            hot_measurements.append(
                (time.perf_counter() - started) * 1000
            )
            response.raise_for_status()

    return {
        "cold_ms": cold_ms,
        "hot_ms": statistics.median(hot_measurements),
        "rss_delta_mib": max(0, rss_after - rss_before) / (1024 * 1024),
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("value must be positive")
    return parsed


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Benchmark irrigation runtime statistics"
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=PROJECT_ROOT / "data/stats/irrigation_runtime",
    )
    parser.add_argument("--hot-runs", type=_positive_int, default=5)
    parser.add_argument("--cold-limit-ms", type=float, default=300)
    parser.add_argument("--hot-limit-ms", type=float, default=100)
    parser.add_argument("--rss-limit-mib", type=float, default=100)
    args = parser.parse_args(argv)

    measurements = run_benchmark(args.runtime_root, args.hot_runs)
    failures = evaluate_budget(
        **measurements,
        cold_limit_ms=args.cold_limit_ms,
        hot_limit_ms=args.hot_limit_ms,
        rss_limit_mib=args.rss_limit_mib,
    )
    print(
        json.dumps(
            {**measurements, "failures": failures},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
