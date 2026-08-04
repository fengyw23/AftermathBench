from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.independent_gap_design import build_independent_gap_design


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the strict pre-runtime Forgejo reconciliation design."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_independent_gap_design(
        scenario_id="forgejo-cross-system-reconciliation-dev-001",
        obligations={
            "actions_bundle_matches_approval": (
                "approval_manifest",
                "actions_artifact",
            ),
            "artifact_registry_matches_bundle": (
                "actions_artifact",
                "deployment_artifact_registry",
            ),
            "production_matches_registry": (
                "deployment_artifact_registry",
                "production_deployment",
            ),
            "attestation_matches_production": (
                "production_deployment",
                "external_attestation",
            ),
            "release_metadata_matches_all_effects": (
                "approval_manifest",
                "production_deployment",
                "external_attestation",
                "release_metadata",
            ),
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload["observed"], ensure_ascii=False))
    return 0 if payload["passed_design_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
