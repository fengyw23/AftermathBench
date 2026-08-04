from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from aftermath_bench.forgejo_promotion_boundary_audit import (
    REQUIRED_VARIANTS,
    audit_forgejo_promotion_boundaries,
)
from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
)


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit six native Forgejo promotion boundary replays."
    )
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prefix = _read(args.prefix)
    instance = ForgejoPromotionInstanceSpec.from_path(args.instance_spec)
    reports: dict[str, dict[str, Any]] = {}
    for variant in sorted(REQUIRED_VARIANTS):
        boundary = _read(args.run_root / f"{variant}-boundary.json")
        reference = _read(args.run_root / f"{variant}-reference.json")
        bundle = _read(args.run_root / f"{variant}-bundle" / "bundle.json")
        issues = boundary["issues"]
        releases = boundary["releases"]
        state = boundary["deployment_state"]
        run = boundary.get("action_run")
        target_artifacts = [
            row for row in state["artifacts"] if row["version"] == instance.version
        ]
        target_deployments = [
            row
            for row in state["deployments"]
            if row["environment"] == instance.production_environment
            and row["desired_version"] == instance.version
            and row["status"] == "deployed"
        ]
        rollout = next(
            item
            for item in issues
            if int(item["number"]) == int(prefix["rollout_issue_index"])
        )
        approval = next(
            item
            for item in issues
            if int(item["number"]) == int(prefix["approval_issue_index"])
        )
        unrelated = next(
            item
            for item in issues
            if int(item["number"]) == int(prefix["unrelated_issue_index"])
        )
        protected_environment = {
            "deployment": [
                row
                for row in state["deployments"]
                if row["environment"] == instance.protected_environment
            ],
            "replicas": [
                row
                for row in state["replicas"]
                if row["environment"] == instance.protected_environment
            ],
        }
        reports[variant] = {
            "dimension_projection": {
                "actions_owner": "absent" if run is None else str(run.get("status")),
                "signed_bundle": "complete" if target_artifacts else "absent",
                "production_deployment": (
                    "complete" if target_deployments else "absent"
                ),
                "external_attestation": (
                    "accepted"
                    if boundary.get("external_attestation") is not None
                    else "absent"
                ),
                "release_metadata": (
                    "closed"
                    if any(
                        release.get("tag_name") == instance.release_tag
                        for release in releases
                    )
                    and rollout.get("state") == "closed"
                    else "absent"
                ),
                "approval_record": str(approval.get("state")),
                "prior_release": str(
                    sum(
                        release.get("tag_name") == instance.protected_release_tag
                        for release in releases
                    )
                ),
                "protected_environment": _fingerprint(protected_environment),
                "unrelated_issue": str(unrelated.get("state")),
            },
            "replay_bound": bool(boundary.get("passed")),
            "native_state_sha256": _fingerprint(bundle),
            "reference_passed": bool(
                reference.get("evaluation", {}).get("recovery_integrity_pass")
            ),
        }
    audit = audit_forgejo_promotion_boundaries(reports)
    payload = {
        "schema_version": "1.0",
        "scenario_id": instance.scenario_id,
        "reports": reports,
        "checks": audit.checks,
        "observed": audit.observed,
        "passed": audit.passed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"scenario_id": instance.scenario_id, "passed": audit.passed}))
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
