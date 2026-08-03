from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.forgejo_migration_state_evidence import (
    build_forgejo_migration_state_evidence,
)
from aftermath_bench.integrations.deployment_target_api import (
    DeploymentTargetAPI,
)
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_migration_evaluator import (
    ForgejoMigrationEvaluator,
)
from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.strict_json import load_json_strict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture hash-bound Forgejo migration state evidence."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--phase", choices=("reset", "boundary"), required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--forgejo-archive", type=Path, required=True)
    parser.add_argument("--deployment-target-archive", type=Path, required=True)
    parser.add_argument("--failure-report", type=Path)
    parser.add_argument("--reset-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-url", default="http://127.0.0.1:9095")
    args = parser.parse_args()

    scenario = load_native_scenario(args.scenario)
    instance = ForgejoMigrationInstanceSpec.from_path(args.instance_spec)
    credentials = load_json_strict(args.credentials)
    prefix = load_json_strict(args.prefix)
    if (
        scenario.family_id != "forgejo-migration-deployment"
        or scenario.scenario_id != instance.scenario_id
        or scenario.raw.get("instance_spec_sha256") != instance.sha256
        or args.variant not in scenario.variants
        or not isinstance(credentials, dict)
        or not credentials.get("base_url")
        or not credentials.get("token")
        or not isinstance(prefix, dict)
        or prefix.get("scenario_id") != scenario.scenario_id
    ):
        raise ValueError(
            "scenario, instance, credentials, prefix and variant do not match"
        )
    evaluator = ForgejoMigrationEvaluator(
        forgejo=ForgejoAPI(
            base_url=str(credentials["base_url"]),
            token=str(credentials["token"]),
        ),
        deployment=DeploymentTargetAPI(args.deployment_url),
        instance=instance,
        prefix=prefix,
    )
    evaluation = evaluator.evaluate(variant=args.variant)
    state = evaluation.get("final_evidence")
    if not isinstance(state, dict):
        raise ValueError("migration evaluator did not expose native state")
    payload = build_forgejo_migration_state_evidence(
        scenario_id=scenario.scenario_id,
        instance_id=scenario.instance_id,
        instance_spec_sha256=instance.sha256,
        variant_id=args.variant,
        phase=args.phase,
        prefix_path=args.prefix,
        bundle_manifest_path=args.bundle_manifest,
        forgejo_archive_path=args.forgejo_archive,
        deployment_target_archive_path=args.deployment_target_archive,
        state=state,
        surface_result=str(
            scenario.raw["ambiguous_operation"]["surface_result"]
        ),
        failure_report_path=args.failure_report,
        reset_evidence_path=args.reset_evidence,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "scenario_id": scenario.scenario_id,
                "instance_id": scenario.instance_id,
                "variant_id": args.variant,
                "phase": args.phase,
                "state_fingerprint": payload["state_fingerprint"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
