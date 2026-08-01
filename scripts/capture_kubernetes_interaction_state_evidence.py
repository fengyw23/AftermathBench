from __future__ import annotations

import argparse
import json
import time
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


def _capture_until_exact(
    *,
    api: KubernetesApi,
    variant: str,
    expected: bytes | None,
    wait_seconds: int,
) -> tuple[dict[str, object], bytes]:
    attempts = wait_seconds + 1 if expected is not None else 1
    payload: dict[str, object] | None = None
    encoded: bytes | None = None
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            payload = build_interaction_boundary_evidence(
                api=api,
                variant_id=variant,
            )
            encoded = _encoded(payload)
            if expected is None or encoded == expected:
                return payload, encoded
        except Exception as error:  # noqa: BLE001
            last_error = error
        if attempt + 1 < attempts:
            time.sleep(1)
    if payload is None or encoded is None:
        raise RuntimeError(
            "could not capture restored Kubernetes boundary: "
            f"variant={variant}, last_error={last_error}"
        )
    raise RuntimeError(
        "restored Kubernetes boundary differs from expected bytes after "
        f"{wait_seconds}s: variant={variant}"
    )


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
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help=(
            "When --expected is supplied, wait up to this many seconds for "
            "controllers to settle to the exact canonical boundary."
        ),
    )
    args = parser.parse_args()
    if args.wait_seconds < 0:
        parser.error("--wait-seconds must be non-negative")
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    expected = args.expected.read_bytes() if args.expected is not None else None
    payload, encoded = _capture_until_exact(
        api=api,
        variant=args.variant,
        expected=expected,
        wait_seconds=args.wait_seconds,
    )
    matches = expected is None or encoded == expected
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
