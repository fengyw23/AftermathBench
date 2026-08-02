from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.kubernetes_replay_drift import (
    compare_kubernetes_replay_states,
)
from aftermath_bench.strict_json import load_json_strict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare one restored Kubernetes state with its frozen boundary."
    )
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-differences", type=int, default=500)
    args = parser.parse_args()
    result = compare_kubernetes_replay_states(
        load_json_strict(args.expected),
        load_json_strict(args.actual),
        maximum_differences=args.maximum_differences,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
