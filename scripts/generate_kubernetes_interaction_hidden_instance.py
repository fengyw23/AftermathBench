"""Generate a private, non-overlapping Kubernetes interaction instance."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def build_instance(instance_id: str) -> dict[str, str]:
    """Return fresh, Kubernetes-safe business identities and scalar facts."""

    token = secrets.token_hex(5)
    suffix = token[-5:]
    current_epoch = 10 + int(token[-2:], 16) % 30
    current_generation = 20 + int(token[-4:-2], 16) % 40
    current_minor = 3 + int(token[-1], 16) % 5
    application = f"ledger{suffix}"
    change_stem = f"{application}-platform"
    prefix = f"{application}-"
    return {
        "scenario_id": f"k8s-constraint-interactions-hidden-{instance_id}-{token}",
        "namespace": f"aftermath-{application}",
        "application": application,
        "change_stem": change_stem,
        "current_version": f"v{current_minor}",
        "target_version": f"v{current_minor + 1}",
        "current_epoch": str(current_epoch),
        "target_epoch": str(current_epoch + 1),
        "current_credential_generation": str(current_generation),
        "target_credential_generation": str(current_generation + 1),
        "batch_id": f"ledger-batch-{int(token[:4], 16) % 9000 + 1000}",
        "api_service": f"{prefix}gateway",
        "current_api_deployment": f"{prefix}api-v{current_minor}",
        "target_api_deployment": f"{prefix}api-v{current_minor + 1}",
        "current_worker_deployment": f"{prefix}worker-v{current_minor}",
        "target_worker_deployment": f"{prefix}worker-v{current_minor + 1}",
        "current_credential": f"{prefix}db-live",
        "next_credential": f"{prefix}db-candidate",
        "backup_job": f"{prefix}backup-e{current_epoch}",
        "migration_generate_name": f"{change_stem}-migration-",
        "transition_job": f"{prefix}worker-handoff",
        "publication_job": f"{prefix}release-publish",
        "service_account": f"{prefix}operator",
        "observer_role": f"{prefix}observer",
        "schema_contract": f"{prefix}schema-contract",
        "compatibility_contract": f"{prefix}compat-contract",
        "credential_contract": f"{prefix}credential-contract",
        "controller_contract": f"{prefix}controller-contract",
        "publication_contract": f"{prefix}publication-contract",
        "audit_contract": f"{prefix}audit-contract",
        "database_catalog": f"{prefix}catalog",
        "compatibility_bridge": f"{prefix}compat-bridge",
        "batch_state": f"{prefix}batch-state",
        "change_record": f"{prefix}change-record",
        "release_ledger": f"{prefix}release-ledger",
        "recovery_audit": f"{prefix}recovery-audit",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    payload = build_instance(args.instance_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"created": True, "instance_id": args.instance_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
