from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.native_baseline_summary import summarize_baselines


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize replayed fixed policies for a native family."
    )
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = summarize_baselines(
        run_directory=args.run_directory,
        scenario=_read(args.scenario),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["coverage_errors"] and not summary["parse_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
