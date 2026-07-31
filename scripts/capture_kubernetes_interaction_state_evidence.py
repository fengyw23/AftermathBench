from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_interaction_evidence import (
    build_interaction_boundary_evidence,
)
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    KUBERNETES_INTERACTION_VARIANTS,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack


def _encoded(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture a canonical, UID-preserving Kubernetes interaction "
            "failure boundary."
        )
    )
    parser.add_argument(
        "--variant",
        choices=KUBERNETES_INTERACTION_VARIANTS,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--expected",
        type=Path,
        help="Require the capture to equal an earlier canonical boundary.",
    )
    args = parser.parse_args()
    stack = KubernetesStack.from_repository()
    payload = build_interaction_boundary_evidence(
        api=KubernetesApi(context=stack.context),
        variant_id=args.variant,
    )
    encoded = _encoded(payload)
    matches = True
    if args.expected is not None:
        expected = args.expected.read_bytes()
        matches = encoded == expected
        if not matches:
            raise RuntimeError(
                "restored Kubernetes boundary differs from expected bytes: "
                f"expected={args.expected}, variant={args.variant}"
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "variant": args.variant,
                "state_sha256": payload["state_sha256"],
                "matches_expected": matches,
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
