from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.model_evidence_import import (
    ModelEvidenceImportError,
    ModelEvidenceImportGate,
    validate_model_artifact,
    validate_source_provenance,
    write_json,
)
from aftermath_bench.strict_json import load_json_strict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate immutable ordinary-model evidence imports."
    )
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--evidence-id")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("gate")
    provenance = subparsers.add_parser("provenance")
    provenance.add_argument("--run-metadata", type=Path, required=True)
    provenance.add_argument("--artifacts-metadata", type=Path, required=True)
    provenance.add_argument("--output", type=Path, required=True)
    artifact = subparsers.add_parser("artifact")
    artifact.add_argument("--stage", type=Path, required=True)
    artifact.add_argument("--root", type=Path, default=Path("."))
    artifact.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        gate = ModelEvidenceImportGate.from_path(args.gate)
        if args.command == "gate":
            print(
                json.dumps(
                    {
                        "passed": True,
                        "source_count": len(gate.sources),
                        "evidence_ids": [source.evidence_id for source in gate.sources],
                    },
                    indent=2,
                )
            )
            return 0
        if not args.evidence_id:
            raise ModelEvidenceImportError("--evidence-id is required")
        source = gate.source(args.evidence_id)
        if args.command == "provenance":
            result = validate_source_provenance(
                load_json_strict(args.run_metadata),
                load_json_strict(args.artifacts_metadata),
                source=source,
            )
        else:
            result = validate_model_artifact(
                args.stage,
                source=source,
                root=args.root,
            )
        write_json(args.output, result)
        print(json.dumps({"passed": True, "evidence_id": source.evidence_id}))
        return 0
    except (OSError, ValueError, ModelEvidenceImportError) as error:
        print(json.dumps({"passed": False, "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
