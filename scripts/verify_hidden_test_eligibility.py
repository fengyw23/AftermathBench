from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.hidden_test_eligibility import (
    verify_hidden_test_eligibility,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reject consumed or development scenarios before a hidden-test "
            "model run."
        )
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--usage-ledger", type=Path, required=True)
    args = parser.parse_args()
    result = verify_hidden_test_eligibility(
        scenario_path=args.scenario,
        freeze_path=args.freeze,
        usage_ledger_path=args.usage_ledger,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
