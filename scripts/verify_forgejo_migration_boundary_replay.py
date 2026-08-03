from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.forgejo_migration_state_evidence import (
    validate_forgejo_migration_boundary_replay,
)
from aftermath_bench.strict_json import load_json_strict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify an exact Forgejo migration boundary replay."
    )
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args()
    boundary = load_json_strict(args.boundary)
    replay = load_json_strict(args.replay)
    result = validate_forgejo_migration_boundary_replay(boundary, replay)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
