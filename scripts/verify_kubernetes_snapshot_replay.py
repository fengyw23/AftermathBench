from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.kubernetes_api import KubernetesApi
from aftermath_bench.integrations.kubernetes_interaction_evidence import (
    build_interaction_boundary_evidence,
)
from aftermath_bench.integrations.kubernetes_interaction_prefix import NAMESPACE
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    KUBERNETES_INTERACTION_VARIANTS,
)
from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    _json_request,
)
from aftermath_bench.integrations.kubernetes_stack import KubernetesStack
from aftermath_bench.schema import repository_root


def _encoded(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _write(path: Path, payload: dict[str, Any]) -> bytes:
    encoded = _encoded(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return encoded


def _capture(api: KubernetesApi, variant: str) -> dict[str, Any]:
    return build_interaction_boundary_evidence(api=api, variant_id=variant)


def _wait_exact_boundary(
    *,
    api: KubernetesApi,
    variant: str,
    expected: bytes,
    output: Path,
    attempts: int = 180,
) -> dict[str, Any]:
    last_error = ""
    last_payload: dict[str, Any] | None = None
    for _attempt in range(attempts):
        try:
            payload = _capture(api, variant)
            last_payload = payload
            observed = _encoded(payload)
            if observed == expected:
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(observed)
                return payload
            last_error = (
                "canonical bytes differ: "
                f"expected={hashlib.sha256(expected).hexdigest()}, "
                f"observed={hashlib.sha256(observed).hexdigest()}"
            )
        except Exception as error:  # noqa: BLE001
            last_error = f"{type(error).__name__}: {error}"
        time.sleep(1)
    if last_payload is not None:
        _write(output, last_payload)
    raise RuntimeError(
        f"Kubernetes boundary did not become byte-exact: {last_error}"
    )


def _destructive_probe(api: KubernetesApi) -> dict[str, Any]:
    deletion = api.delete("namespace", NAMESPACE)
    api.wait_deleted("namespace", NAMESPACE, timeout="180s")
    external = _json_request(
        "http://127.0.0.1:9092/webhooks/events",
        method="POST",
        payload={"probe": "must-disappear-after-restore"},
        headers={"X-Idempotency-Key": "k0:destructive-probe"},
    )
    return {"namespace_deletion": deletion, "external_write": external}


def _run_reference(*, variant: str, output: Path) -> dict[str, Any]:
    command = (
        sys.executable,
        str(repository_root() / "scripts" / "run_kubernetes_interaction_control.py"),
        "--variant",
        variant,
        "--output",
        str(output),
    )
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        cwd=repository_root(),
    )
    if completed.returncode:
        raise RuntimeError(
            "reference recovery failed after exact restore:\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    payload = json.loads(output.read_text(encoding="utf-8"))
    if not payload.get("evaluation", {}).get("passed"):
        raise RuntimeError("reference report did not pass after restore")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prove two-cycle exact replay of a Kubernetes and external-ledger "
            "failure boundary."
        )
    )
    parser.add_argument(
        "--variant",
        choices=KUBERNETES_INTERACTION_VARIANTS,
        default="state_13",
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--registry-database", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)

    original_payload = _capture(api, args.variant)
    original = _write(output / "boundary-original.json", original_payload)
    bundle_manifest = stack.snapshot_bundle(
        args.bundle,
        registry_database=args.registry_database,
    )

    destructive = _destructive_probe(api)
    _write(output / "destructive-probe-1.json", destructive)
    first_restore = stack.restore_bundle(
        args.bundle,
        registry_database=args.registry_database,
    )
    first = _wait_exact_boundary(
        api=api,
        variant=args.variant,
        expected=original,
        output=output / "boundary-restored-1.json",
    )
    reference = _run_reference(
        variant=args.variant,
        output=output / "reference-after-restore.json",
    )

    second_restore = stack.restore_bundle(
        args.bundle,
        registry_database=args.registry_database,
    )
    second = _wait_exact_boundary(
        api=api,
        variant=args.variant,
        expected=original,
        output=output / "boundary-restored-2.json",
    )

    result = {
        "schema_version": "1.0",
        "variant": args.variant,
        "passed": True,
        "checks": {
            "first_restore_byte_exact": _encoded(first) == original,
            "second_restore_byte_exact": _encoded(second) == original,
            "uid_bearing_state_preserved": (
                first["state"]["boundary_facts"]
                == original_payload["state"]["boundary_facts"]
            ),
            "external_registry_preserved": (
                first["state"]["external_deliveries"]
                == original_payload["state"]["external_deliveries"]
            ),
            "reference_passed_from_restored_boundary": bool(
                reference["evaluation"]["passed"]
            ),
            "reference_mutated_restored_boundary": bool(
                reference.get("mutation_tools")
            ),
        },
        "bundle_manifest": bundle_manifest,
        "first_restore": first_restore,
        "second_restore": second_restore,
    }
    result["passed"] = all(result["checks"].values())
    _write(output / "summary.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
