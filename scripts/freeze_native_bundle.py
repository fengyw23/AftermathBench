from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.native_freeze import (
    append_usage_event,
    build_frozen_bundle,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze an exact native evaluator bundle before models."
    )
    parser.add_argument("--bundle-root", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--runtime-revision", required=True)
    parser.add_argument("--private-attestation", type=Path, required=True)
    parser.add_argument("--public-commitment", type=Path, required=True)
    parser.add_argument("--usage-ledger", type=Path, required=True)
    parser.add_argument("--salt")
    args = parser.parse_args()
    bundle = build_frozen_bundle(
        bundle_root=args.bundle_root,
        scenario_path=args.scenario,
        instance_spec_path=args.instance_spec,
        source_commit=args.source_commit,
        runtime_revision=args.runtime_revision,
        salt=args.salt,
        excluded_relative_paths=(
            args.private_attestation.resolve()
            .relative_to(args.bundle_root.resolve())
            .as_posix(),
            args.public_commitment.resolve()
            .relative_to(args.bundle_root.resolve())
            .as_posix(),
            args.usage_ledger.resolve()
            .relative_to(args.bundle_root.resolve())
            .as_posix(),
        ),
    )
    _write(args.private_attestation, bundle.private_attestation)
    _write(args.public_commitment, bundle.public_commitment)
    append_usage_event(
        ledger_path=args.usage_ledger,
        event="frozen",
        details={
            "public_commitment_sha256": bundle.public_commitment[
                "public_commitment_sha256"
            ]
        },
    )
    print(
        json.dumps(
            {
                "scenario_id": bundle.public_commitment["scenario_id"],
                "public_commitment_sha256": bundle.public_commitment[
                    "public_commitment_sha256"
                ],
                "bound_file_count": bundle.public_commitment[
                    "bound_file_count"
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
