from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_package_provenance_instance import (
    package_provenance_blueprint,
)
from aftermath_bench.integrations.forgejo_publication_instance import (
    ForgejoPublicationInstanceSpec,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument(
        "--benchmark-split",
        choices=("development", "public_dev", "hidden_test"),
        required=True,
    )
    parser.add_argument("--hidden-test-eligible", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    instance = ForgejoPublicationInstanceSpec.from_path(args.instance_spec)
    payload = package_provenance_blueprint(
        instance,
        instance_id=args.instance_id,
        benchmark_split=args.benchmark_split,
        hidden_test_eligible=args.hidden_test_eligible,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
