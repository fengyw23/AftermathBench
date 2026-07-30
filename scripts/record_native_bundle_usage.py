from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.native_freeze import append_usage_event


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Append a lifecycle event to a native bundle ledger."
    )
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument(
        "--event",
        choices=(
            "generated",
            "frozen",
            "evaluation_locked",
            "consumed",
            "retired",
        ),
        required=True,
    )
    parser.add_argument("--details-json", default="{}")
    args = parser.parse_args()
    details = json.loads(args.details_json)
    if not isinstance(details, dict):
        raise ValueError("--details-json must decode to an object")
    record = append_usage_event(
        ledger_path=args.ledger,
        event=args.event,
        details=details,
    )
    print(json.dumps(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
