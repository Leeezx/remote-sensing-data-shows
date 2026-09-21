from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.readiness import collect_readiness_failures  # noqa: E402


def main() -> int:
    failures = collect_readiness_failures()
    if failures:
        print(f"missing or invalid: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("Deployment data ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
