from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_interacting_recovery_design import (
    build_forgejo_interacting_recovery_design,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the pre-runtime interacting Forgejo recovery design."
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = build_forgejo_interacting_recovery_design()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0 if payload["passed_design_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
