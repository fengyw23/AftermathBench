from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.formal_evidence_builder import (
    build_formal_evidence,
    build_formal_inputs,
    complete_formal_evidence,
    load_formal_evidence_build_spec,
)
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a hash-bound seven-role formal-evidence package. "
            "This command never promotes development evidence or edits the "
            "release manifest."
        )
    )
    parser.add_argument(
        "--spec",
        type=Path,
        required=True,
        help="Strict JSON formal-evidence build specification.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=repository_root(),
        help="Repository root (defaults to the installed checkout).",
    )
    parser.add_argument(
        "--phase",
        choices=("inputs", "complete", "one-shot"),
        default="one-shot",
        help=(
            "inputs freezes the five pre-model roles; complete verifies that "
            "lock and appends run evidence; one-shot executes both phases."
        ),
    )
    args = parser.parse_args()
    spec = load_formal_evidence_build_spec(args.spec)
    if args.phase == "inputs":
        result = build_formal_inputs(spec, root=args.root)
    elif args.phase == "complete":
        result = complete_formal_evidence(spec, root=args.root)
    else:
        result = build_formal_evidence(spec, root=args.root)
    print(
        json.dumps(
            result.as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
