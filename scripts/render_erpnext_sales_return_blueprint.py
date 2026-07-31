from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_sales_return_instance import (
    ERPNextSalesReturnInstanceSpec,
    sales_return_blueprint,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render one ERPNext sales-return blueprint from its spec."
    )
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument(
        "--benchmark-split",
        choices=("development", "public_dev", "hidden_test"),
        required=True,
    )
    args = parser.parse_args()
    instance = ERPNextSalesReturnInstanceSpec.from_path(args.instance_spec)
    payload = sales_return_blueprint(
        instance,
        instance_id=args.instance_id,
        benchmark_split=args.benchmark_split,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario_id": instance.scenario_id,
                "instance_id": args.instance_id,
                "instance_spec_sha256": instance.sha256,
                "benchmark_split": args.benchmark_split,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
