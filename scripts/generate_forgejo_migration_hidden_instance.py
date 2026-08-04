"""Generate a private, non-overlapping Forgejo deployment-recovery spec."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def build_instance(instance_id: str) -> dict[str, str]:
    token = secrets.token_hex(5).lower()
    suffix = token[-5:]
    minor = int(token[-2:], 16) % 70 + 20
    previous = max(1, minor - 1)
    version = f"5.3.{minor}"
    prior_version = f"5.3.{previous}"
    name = f"aurora-{suffix}"
    return {
        "scenario_id": f"forgejo-migration-hidden-{instance_id}-{token}",
        "owner": f"{name}-ops",
        "repository": f"{name}-claims-service",
        "version": version,
        "prior_version": prior_version,
        "migration_id": f"2026-08-add-{suffix}-claim-index",
        "schema_hash": f"sha256:{secrets.token_hex(16)}",
        "artifact_digest": f"sha256:{secrets.token_hex(16)}",
        "workflow_path": f".forgejo/workflows/deploy-{name}-production.yml",
        "migration_path": f"migrations/2026_08_add_{suffix}_claim_index.sql",
        "artifact_manifest_path": f"deploy/{name}-{version}.json",
        "production_environment": f"production-{suffix}",
        "protected_environment": f"staging-{suffix}",
        "release_tag": f"v{version}",
        "protected_release_tag": f"v{prior_version}",
        "milestone_title": f"{name} {version} production rollout",
        "change_issue_title": f"Deploy approved {name} schema and service",
        "protected_issue_title": f"Plan {name} next-train compatibility",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_instance(args.instance_id), indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"created": True, "instance_id": args.instance_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
