from __future__ import annotations

import sys

from backend.readiness import collect_readiness_failures


def main() -> int:
    failures = collect_readiness_failures()
    if failures:
        print(f"missing or invalid: {', '.join(failures)}", file=sys.stderr)
        return 1
    print("Deployment data ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
