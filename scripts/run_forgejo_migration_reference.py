from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_migration_evaluator import (
    ForgejoMigrationEvaluator,
)
from aftermath_bench.integrations.forgejo_migration_faults import (
    FORGEJO_MIGRATION_VARIANTS,
)
from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)
from aftermath_bench.integrations.forgejo_migration_recovery import (
    ForgejoMigrationReferenceAgent,
)
from aftermath_bench.integrations.forgejo_stack import ForgejoStack
from aftermath_bench.schema import repository_root


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the reference recovery for a Forgejo migration boundary."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument(
        "--variant", choices=FORGEJO_MIGRATION_VARIANTS, required=True
    )
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
    stack = ForgejoStack(
        compose_file=repository_root() / "runtimes" / "forgejo" / "compose.yaml"
    )
    trace = ForgejoMigrationReferenceAgent(
        forgejo=forgejo,
        deployment=deployment,
        stack=stack,
        instance=instance,
        prefix=prefix,
    ).recover()
    evaluation = ForgejoMigrationEvaluator(
        forgejo=forgejo,
        deployment=deployment,
        instance=instance,
        prefix=prefix,
    ).evaluate(variant=args.variant)
    payload = {
        "schema_version": "1.0",
        "variant": args.variant,
        "trace": trace,
        "evaluation": evaluation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "mutations": sum(item["kind"] == "write" for item in trace),
                "recovery_integrity_pass": evaluation[
                    "recovery_integrity_pass"
                ],
            }
        )
    )
    return 0 if evaluation["recovery_integrity_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
