from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.kubernetes_constraint_analysis import (
    analyze_kubernetes_constraint_runs,
    load_run_reports,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze_kubernetes_constraint_runs(
        load_run_reports(args.run_directory)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["completed_runs"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
