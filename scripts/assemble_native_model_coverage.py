from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.model_coverage_assembly import (
    TrajectorySource,
    assemble_model_coverage,
)


def _source(value: str, *, role: str) -> TrajectorySource:
    try:
        run_id, root = value.split("=", 1)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected RUN_ID=DIRECTORY") from error
    if not run_id.strip() or not root.strip():
        raise argparse.ArgumentTypeError("expected RUN_ID=DIRECTORY")
    return TrajectorySource(run_id=run_id.strip(), root=Path(root), role=role)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fill provider-missing native trajectories without replacing any "
            "scored primary trajectory."
        )
    )
    parser.add_argument("--primary", required=True, help="RUN_ID=DIRECTORY")
    parser.add_argument("--retry", action="append", default=[], help="RUN_ID=DIRECTORY")
    parser.add_argument("--expected-variant", action="append", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()

    manifest = assemble_model_coverage(
        primary=_source(args.primary, role="primary"),
        retries=[_source(value, role="provider_retry") for value in args.retry],
        expected_variants=set(args.expected_variant),
        output_root=args.output_directory,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
