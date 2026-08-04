from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
)
from aftermath_bench.integrations.forgejo_reconciliation_instance import (
    reconciliation_blueprint,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--benchmark-split",
        choices=("development", "public_dev", "hidden_test"),
        default="public_dev",
    )
    args = parser.parse_args()
    instance = ForgejoPromotionInstanceSpec.from_path(args.instance_spec)
    payload = reconciliation_blueprint(
        instance,
        instance_id=args.instance_id,
        benchmark_split=args.benchmark_split,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"scenario_id": payload["scenario_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
