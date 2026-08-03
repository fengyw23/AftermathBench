from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.erpnext_manufacturing_state_evidence import (
    validate_manufacturing_boundary_replay,
)
from aftermath_bench.strict_json import load_json_strict


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that an ERPNext manufacturing boundary recapture is "
            "semantically identical and bound to the same exact sources."
        )
    )
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args()
    result = validate_manufacturing_boundary_replay(
        load_json_strict(args.boundary),
        load_json_strict(args.replay),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
