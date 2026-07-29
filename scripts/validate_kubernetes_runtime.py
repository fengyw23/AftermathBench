from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_rollout_prefix import (
    capture_prefix,
    mutate_prefix,
    prefix_fingerprint,
    reset_prefix,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=("reset", "mutate", "capture", "validate-reset"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    if args.action == "reset":
        payload = reset_prefix(api)
    elif args.action == "mutate":
        payload = mutate_prefix(api)
    elif args.action == "capture":
        state = capture_prefix(api)
        payload = {"state": state, "fingerprint": prefix_fingerprint(state)}
    else:
        first = reset_prefix(api)
        mutation = mutate_prefix(api)
        mutated_state = capture_prefix(api)
        mutated_fingerprint = prefix_fingerprint(mutated_state)
        second = reset_prefix(api)
        payload = {
            "first_fingerprint": first["fingerprint"],
            "mutated_fingerprint": mutated_fingerprint,
            "second_fingerprint": second["fingerprint"],
            "mutation": mutation,
            "passed": (
                first["fingerprint"] == second["fingerprint"]
                and first["fingerprint"] != mutated_fingerprint
            ),
        }
        if not payload["passed"]:
            raise RuntimeError("Kubernetes native reset is not deterministic")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
