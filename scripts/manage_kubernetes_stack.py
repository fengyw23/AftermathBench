from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "up",
            "down",
            "status",
            "prepare-snapshot-runtime",
            "snapshot-bundle",
            "restore-bundle",
        ),
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--registry-database", type=Path)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    if args.action == "up":
        payload = stack.up()
    elif args.action == "down":
        stack.down()
        payload = {"deleted": stack.cluster_name}
    elif args.action == "prepare-snapshot-runtime":
        payload = stack.prepare_snapshot_runtime()
    elif args.action == "snapshot-bundle":
        if args.snapshot is None or args.registry_database is None:
            parser.error(
                "snapshot-bundle requires --snapshot and --registry-database"
            )
        payload = stack.snapshot_bundle(
            args.snapshot,
            registry_database=args.registry_database,
        )
    elif args.action == "restore-bundle":
        if args.snapshot is None or args.registry_database is None:
            parser.error(
                "restore-bundle requires --snapshot and --registry-database"
            )
        payload = stack.restore_bundle(
            args.snapshot,
            registry_database=args.registry_database,
        )
    else:
        payload = {
            "cluster_name": stack.cluster_name,
            "exists": stack.cluster_name in stack.clusters(),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
