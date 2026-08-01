from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_instance import (
    KubernetesInteractionInstanceSpec,
    kubernetes_interaction_blueprint,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument(
        "--benchmark-split",
        choices=("development", "public_dev", "hidden_test"),
        required=True,
    )
    args = parser.parse_args()
    instance = KubernetesInteractionInstanceSpec.from_path(args.instance_spec)
    payload = kubernetes_interaction_blueprint(
        instance,
        instance_id=args.instance_id,
        benchmark_split=args.benchmark_split,
        hidden_test_eligible=args.benchmark_split == "hidden_test",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "scenario_id": instance.scenario_id,
                "instance_spec_sha256": instance.sha256,
                "matched_variants": len(payload["matched_variants"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
