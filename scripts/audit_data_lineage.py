from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.data_lineage import build_data_lineage_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit active scenario data provenance and native generation lineage."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. The report is printed when omitted.",
    )
    args = parser.parse_args()
    report = build_data_lineage_audit()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
