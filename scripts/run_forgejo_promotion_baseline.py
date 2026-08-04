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
from aftermath_bench.integrations.forgejo_promotion_baselines import (
    FORGEJO_PROMOTION_BASELINES,
    run_fixed_forgejo_promotion_baseline,
)
from aftermath_bench.integrations.forgejo_promotion_faults import (
    FORGEJO_PROMOTION_VARIANTS,
)
from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
)
from aftermath_bench.integrations.forgejo_stack import ForgejoStack
from aftermath_bench.schema import repository_root


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected object in {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--variant", choices=FORGEJO_PROMOTION_VARIANTS, required=True)
    parser.add_argument(
        "--baseline", choices=FORGEJO_PROMOTION_BASELINES, required=True
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-url", default="http://127.0.0.1:9095")
    parser.add_argument("--external-url", default="http://127.0.0.1:9092")
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    instance = ForgejoPromotionInstanceSpec.from_path(args.instance_spec)
    environment = ForgejoPromotionEnvironment(
        forgejo=ForgejoAPI(
            base_url=str(credentials["base_url"]), token=str(credentials["token"])
        ),
        deployment=DeploymentTargetAPI(args.deployment_url),
        stack=ForgejoStack(
            compose_file=repository_root() / "runtimes" / "forgejo" / "compose.yaml"
        ),
        instance=instance,
        prefix=prefix,
        variant=args.variant,
        external_url=args.external_url,
    )
    trace = run_fixed_forgejo_promotion_baseline(args.baseline, environment=environment)
    final_state = environment.snapshot()
    evaluation = final_state["evaluation"]
    payload = {
        "schema_version": "1.0",
        "variant": args.variant,
        "baseline": args.baseline,
        "trace": trace,
        "evaluation": evaluation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "baseline": args.baseline,
                "passed": evaluation["passed"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
