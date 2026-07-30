from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.evidence_manifest import build_file_manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a relative-path SHA-256 manifest for evidence."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Additional root-relative path to omit. Repeat as needed for "
            "metadata that refers to the manifest and would be circular."
        ),
    )
    args = parser.parse_args()
    try:
        relative_output = args.output.relative_to(args.root).as_posix()
    except ValueError:
        relative_output = ""
    result = build_file_manifest(
        args.root,
        exclude=(
            ({relative_output} if relative_output else set())
            | set(args.exclude)
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
