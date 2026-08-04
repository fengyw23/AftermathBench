from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_promotion_agent import (
    ForgejoPromotionEnvironment,
)
from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
)
from aftermath_bench.integrations.forgejo_reconciliation_faults import (
    FORGEJO_RECONCILIATION_VARIANTS,
)
from aftermath_bench.integrations.forgejo_reconciliation_recovery import (
    collect_reconciliation_state,
    evaluate_reconciliation_terminal,
    reference_reconciliation_recovery,
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
        description="Replay the state-driven Forgejo reconciliation reference."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument(
        "--variant", choices=tuple(FORGEJO_RECONCILIATION_VARIANTS), required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-url", default="http://127.0.0.1:9095")
    parser.add_argument("--external-url", default="http://127.0.0.1:9092")
    args = parser.parse_args()

    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    instance = ForgejoPromotionInstanceSpec.from_path(args.instance_spec)
    forgejo = ForgejoAPI(
        base_url=str(credentials["base_url"]), token=str(credentials["token"])
    )
    deployment = DeploymentTargetAPI(args.deployment_url)
    stack = ForgejoStack(
        compose_file=repository_root() / "runtimes" / "forgejo" / "compose.yaml"
    )
    environment = ForgejoPromotionEnvironment(
        forgejo=forgejo,
        deployment=deployment,
        stack=stack,
        instance=instance,
        prefix=prefix,
        variant=args.variant,
        external_url=args.external_url,
    )
    trace = reference_reconciliation_recovery(environment)
    state = collect_reconciliation_state(
        forgejo=forgejo,
        deployment=deployment,
        instance=instance,
        prefix=prefix,
        external_url=args.external_url,
    )
    evaluation = evaluate_reconciliation_terminal(
        state, instance=instance, prefix=prefix
    )
    payload = {
        "schema_version": "0.1",
        "artifact_type": "forgejo_cross_system_reconciliation_reference",
        "scenario_id": f"{instance.scenario_id}--reconciliation",
        "variant": args.variant,
        "reference_trace": trace,
        "final_state": state,
        "evaluation": evaluation,
        "passed": evaluation["passed"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {"variant": args.variant, "passed": evaluation["passed"]},
            ensure_ascii=False,
        )
    )
    return 0 if evaluation["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
