from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.k5_evidence_import import (
    K5EvidenceImportGate,
    build_k5_import_provenance,
    select_k4_artifact_metadata,
    validate_k4_artifact_layout,
    validate_k4_public_summary,
    validate_k4_run_metadata,
)
from aftermath_bench.strict_json import load_json_strict


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and normalize a reviewed Kubernetes K5 import."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gate_parser = subparsers.add_parser("gate")
    gate_parser.add_argument("--gate", type=Path, required=True)
    gate_parser.add_argument("--github-env", type=Path)

    provenance_parser = subparsers.add_parser("provenance")
    provenance_parser.add_argument("--gate", type=Path, required=True)
    provenance_parser.add_argument("--run-metadata", type=Path, required=True)
    provenance_parser.add_argument(
        "--artifacts-metadata", type=Path, required=True
    )
    provenance_parser.add_argument("--import-commit", required=True)
    provenance_parser.add_argument("--output", type=Path, required=True)

    artifact_parser = subparsers.add_parser("artifact")
    artifact_parser.add_argument("--gate", type=Path, required=True)
    artifact_parser.add_argument("--stage", type=Path, required=True)
    artifact_parser.add_argument(
        "--allow-missing-completion",
        action="store_true",
        help=(
            "Allow a scientifically complete K4 artifact whose formal "
            "completion failed after model execution."
        ),
    )

    args = parser.parse_args()
    gate = K5EvidenceImportGate.from_path(args.gate)
    if args.command == "gate":
        environment = gate.github_environment()
        if args.github_env is not None:
            with args.github_env.open("a", encoding="utf-8") as handle:
                for key, value in environment.items():
                    handle.write(f"{key}={value}\n")
        print(json.dumps(environment, sort_keys=True))
        return 0
    if args.command == "provenance":
        run = load_json_strict(args.run_metadata)
        artifacts = load_json_strict(args.artifacts_metadata)
        validate_k4_run_metadata(run, gate=gate)
        artifact = select_k4_artifact_metadata(artifacts, gate=gate)
        provenance = build_k5_import_provenance(
            gate=gate,
            artifact=artifact,
            import_gate_commit=args.import_commit,
        )
        _write_json(args.output, provenance)
        print(json.dumps(provenance, sort_keys=True))
        return 0
    paths = validate_k4_artifact_layout(
        args.stage,
        require_completion=not args.allow_missing_completion,
    )
    summary = load_json_strict(paths["summary"])
    validate_k4_public_summary(summary, gate=gate)
    print(
        json.dumps(
            {key: path.as_posix() for key, path in paths.items()},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
