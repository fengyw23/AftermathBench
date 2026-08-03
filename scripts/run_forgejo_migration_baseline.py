from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_migration_baselines import (
    FORGEJO_MIGRATION_BASELINES,
    ForgejoMigrationBaselineAgent,
)
from aftermath_bench.integrations.forgejo_migration_evaluator import (
    ForgejoMigrationEvaluator,
)
from aftermath_bench.integrations.forgejo_migration_faults import (
    FORGEJO_MIGRATION_VARIANTS,
)
from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)
from aftermath_bench.integrations.forgejo_stack import ForgejoStack
from aftermath_bench.schema import repository_root


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline", choices=FORGEJO_MIGRATION_BASELINES, required=True
    )
    parser.add_argument(
        "--variant", choices=FORGEJO_MIGRATION_VARIANTS, required=True
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--deployment-url", default="http://127.0.0.1:9095"
    )
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    instance = ForgejoMigrationInstanceSpec.from_path(args.instance_spec)
    forgejo = ForgejoAPI(
        base_url=str(credentials["base_url"]),
        token=str(credentials["token"]),
    )
    deployment = DeploymentTargetAPI(args.deployment_url)
    agent = ForgejoMigrationBaselineAgent(
        forgejo=forgejo,
        deployment=deployment,
        stack=ForgejoStack(
            compose_file=repository_root()
            / "runtimes"
            / "forgejo"
            / "compose.yaml"
        ),
        instance=instance,
        prefix=prefix,
    )
    error = None
    try:
        trace = list(agent.run(args.baseline))
    except Exception as caught:  # noqa: BLE001 - expected policy failures are data
        trace = list(agent.trace)
        error = {
            "exception_type": type(caught).__name__,
            "error": str(caught),
        }
    evaluation = ForgejoMigrationEvaluator(
        forgejo=forgejo,
        deployment=deployment,
        instance=instance,
        prefix=prefix,
    ).evaluate(variant=args.variant)
    report = {
        "schema_version": "1.0",
        "artifact_type": "forgejo_migration_baseline",
        "scenario_id": instance.scenario_id,
        "variant": args.variant,
        "baseline": args.baseline,
        "trace": trace,
        "baseline_error": error,
        "evaluation": evaluation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "baseline": args.baseline,
                "passed": evaluation["recovery_integrity_pass"],
                "baseline_error": error,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
