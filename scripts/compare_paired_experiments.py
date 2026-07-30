from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.paired_experiment import (
    compare_paired_experiments,
    load_experiment_metadata,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and compare paired execution-control runs."
    )
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--ordinary-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    control = load_experiment_metadata(
        args.control_directory,
        condition="control",
    )
    ordinary = load_experiment_metadata(
        args.ordinary_directory,
        condition="ordinary",
    )
    result = compare_paired_experiments(control, ordinary)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["valid_pair"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
