from __future__ import annotations

import argparse
import json

from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("up", "down", "status"))
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    if args.action == "up":
        payload = stack.up()
    elif args.action == "down":
        stack.down()
        payload = {"deleted": stack.cluster_name}
    else:
        payload = {
            "cluster_name": stack.cluster_name,
            "exists": stack.cluster_name in stack.clusters(),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
