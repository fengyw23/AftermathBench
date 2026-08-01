from __future__ import annotations

import argparse
import hashlib
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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_object(path: Path, *, label: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a JSON object")
    return value


def _state_sha256(state: dict[str, object]) -> str:
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _formal_capture(
    *,
    native: dict[str, object],
    phase: str,
    variant: str,
    prefix_path: Path,
    bundle_manifest_path: Path,
    reset_evidence_path: Path | None,
    failure_report_path: Path | None,
    pre_snapshot_path: Path | None,
) -> dict[str, object]:
    prefix = _strict_object(prefix_path, label="prefix")
    bundle = _strict_object(bundle_manifest_path, label="bundle manifest")
    if prefix.get("scenario_id") != native.get("scenario_id"):
        raise ValueError("prefix and native capture scenario identities differ")
    state = native.get("state")
    if not isinstance(state, dict) or native.get("state_sha256") != _state_sha256(state):
        raise ValueError("native Kubernetes state fingerprint is invalid")
    if pre_snapshot_path is not None:
        pre_snapshot = _strict_object(
            pre_snapshot_path,
            label="pre-snapshot native state",
        )
        if pre_snapshot.get("state") != state:
            raise ValueError("restored native state differs from the pre-snapshot state")
    common: dict[str, object] = {
        "schema_version": "1.0",
        "artifact_type": "kubernetes_interaction_state_evidence",
        "scenario_id": native["scenario_id"],
        "variant_id": variant,
        "phase": phase,
        "normalization_contract": native["normalization_contract"],
        "prefix_file_sha256": _sha256(prefix_path),
        "bundle_manifest_file_sha256": _sha256(bundle_manifest_path),
        "bundle": bundle,
        "state_sha256": native["state_sha256"],
        "state": state,
    }
    if pre_snapshot_path is not None:
        common["pre_snapshot_state_file_sha256"] = _sha256(pre_snapshot_path)
    if phase == "reset":
        if reset_evidence_path is not None or failure_report_path is not None:
            raise ValueError("reset capture cannot bind boundary-only evidence")
        common["reset_verified"] = True
        return common
    if phase != "boundary":
        raise ValueError(f"unsupported formal capture phase: {phase}")
    if reset_evidence_path is None or failure_report_path is None:
        raise ValueError("boundary capture requires reset evidence and failure report")
    reset = _strict_object(reset_evidence_path, label="reset evidence")
    failure = _strict_object(failure_report_path, label="failure report")
    visible = failure.get("visible_failure")
    if (
        reset.get("phase") != "reset"
        or reset.get("scenario_id") != native.get("scenario_id")
        or reset.get("variant_id") != variant
        or failure.get("scenario_id") != native.get("scenario_id")
        or failure.get("variant") != variant
        or not isinstance(visible, dict)
        or visible.get("ok") is not False
    ):
        raise ValueError("boundary evidence identities or visible failure are invalid")
    common.update(
        {
            "boundary_validation_passed": failure.get("passed") is True,
            "reset_evidence_file_sha256": _sha256(reset_evidence_path),
            "failure_report_file_sha256": _sha256(failure_report_path),
            "surface_result": failure.get("surface_result"),
            "visible_failure": visible,
        }
    )
    return common


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
        "--phase",
        choices=("native", "reset", "boundary"),
        default="native",
        help="Emit the historical native capture or a hash-bound formal capture.",
    )
    parser.add_argument("--prefix", type=Path)
    parser.add_argument("--bundle-manifest", type=Path)
    parser.add_argument("--reset-evidence", type=Path)
    parser.add_argument("--failure-report", type=Path)
    parser.add_argument(
        "--pre-snapshot-state",
        type=Path,
        help="Require the restored canonical state to match this earlier capture.",
    )
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
    if args.phase != "native" and (
        args.prefix is None or args.bundle_manifest is None
    ):
        parser.error("formal reset/boundary captures require --prefix and --bundle-manifest")
    if args.phase == "native" and any(
        value is not None
        for value in (
            args.prefix,
            args.bundle_manifest,
            args.reset_evidence,
            args.failure_report,
            args.pre_snapshot_state,
        )
    ):
        parser.error("formal binding arguments require --phase reset or boundary")
    stack = KubernetesStack.from_repository()
    api = KubernetesApi(context=stack.context)
    expected = args.expected.read_bytes() if args.expected is not None else None
    native_expected = None
    if args.phase == "native":
        native_expected = expected
    elif args.pre_snapshot_state is not None:
        expected_native = _strict_object(
            args.pre_snapshot_state,
            label="pre-snapshot native state",
        )
        expected_native["variant_id"] = args.variant
        native_expected = _encoded(expected_native)
    native, native_encoded = _capture_until_exact(
        api=api,
        variant=args.variant,
        expected=native_expected,
        wait_seconds=args.wait_seconds,
    )
    if args.phase == "native":
        payload = native
        encoded = native_encoded
    else:
        assert args.prefix is not None
        assert args.bundle_manifest is not None
        payload = _formal_capture(
            native=native,
            phase=args.phase,
            variant=args.variant,
            prefix_path=args.prefix,
            bundle_manifest_path=args.bundle_manifest,
            reset_evidence_path=args.reset_evidence,
            failure_report_path=args.failure_report,
            pre_snapshot_path=args.pre_snapshot_state,
        )
        encoded = _encoded(payload)
        if expected is not None and encoded != expected:
            raise RuntimeError(
                "restored formal Kubernetes evidence differs from expected bytes: "
                f"variant={args.variant}, phase={args.phase}"
            )
    matches = expected is None or encoded == expected
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                "variant": args.variant,
                "state_sha256": payload["state_sha256"],
                "phase": args.phase,
                "matches_expected": matches,
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
