from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.forgejo_evidence_import import (
    ForgejoEvidenceImportGate,
    build_import_provenance,
    select_artifact,
    validate_artifact_layout,
    validate_source_run,
)
from aftermath_bench.strict_json import load_json_strict


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a reviewed Forgejo evidence import."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate_parser = subparsers.add_parser("gate")
    gate_parser.add_argument("--gate", type=Path, required=True)
    gate_parser.add_argument("--github-env", type=Path)
    provenance = subparsers.add_parser("provenance")
    provenance.add_argument("--gate", type=Path, required=True)
    provenance.add_argument("--run-metadata", type=Path, required=True)
    provenance.add_argument("--artifacts-metadata", type=Path, required=True)
    provenance.add_argument("--import-commit", required=True)
    provenance.add_argument("--output", type=Path, required=True)
    artifact = subparsers.add_parser("artifact")
    artifact.add_argument("--gate", type=Path, required=True)
    artifact.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    gate = ForgejoEvidenceImportGate.from_path(args.gate)
    if args.command == "gate":
        environment = gate.github_environment()
        if args.github_env is not None:
            with args.github_env.open("a", encoding="utf-8") as stream:
                for key, value in environment.items():
                    stream.write(f"{key}={value}\n")
        print(json.dumps(environment, sort_keys=True))
        return 0
    if args.command == "provenance":
        run = load_json_strict(args.run_metadata)
        artifacts = load_json_strict(args.artifacts_metadata)
        validate_source_run(run, gate=gate)
        selected = select_artifact(artifacts, gate=gate)
        value = build_import_provenance(
            gate=gate, artifact=selected, import_commit=args.import_commit
        )
        _write(args.output, value)
        print(json.dumps(value, sort_keys=True))
        return 0
    paths = validate_artifact_layout(args.stage, gate=gate)
    print(
        json.dumps(
            {key: path.as_posix() for key, path in paths.items()}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
