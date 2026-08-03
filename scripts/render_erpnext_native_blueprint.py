from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_native_instance import (
    ERPNextNativeInstanceSpec,
    render_erpnext_native_blueprint,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a private ERPNext family blueprint from its instance spec."
    )
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument(
        "--benchmark-split",
        choices=("development", "public_dev", "hidden_test"),
        required=True,
    )
    args = parser.parse_args()
    instance = ERPNextNativeInstanceSpec.from_path(args.instance_spec)
    template = json.loads(args.template.read_text(encoding="utf-8"))
    payload = render_erpnext_native_blueprint(
        instance,
        template=template,
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
                "family": instance.family,
                "instance_id": args.instance_id,
                "instance_spec_sha256": instance.sha256,
                "benchmark_split": args.benchmark_split,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
