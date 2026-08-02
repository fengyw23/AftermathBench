from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.formal_release_binding import (
    generate_formal_release_binding,
)
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a deterministic release-slot binding from a validated "
            "native scenario and its completed seven-role evidence package."
        )
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--formal-declarations", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=repository_root())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    binding = generate_formal_release_binding(
        root=args.root,
        scenario_path=args.scenario,
        declarations_path=args.formal_declarations,
    )
    encoded = json.dumps(
        binding,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
