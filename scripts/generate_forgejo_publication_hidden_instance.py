"""Generate a novel private Forgejo release-publication instance spec."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def build_instance(instance_id: str) -> dict[str, str]:
    token = secrets.token_hex(5).lower()
    stem = f"cobalt-{token}"
    release_number = int(token[-2:], 16) % 90 + 10
    protected_release_number = int(token[-4:-2], 16) % 90 + 10
    return {
        "scenario_id": f"forgejo-publication-hidden-{instance_id}-{token}",
        "owner": f"{stem}-ops",
        "repository": f"release-catalog-{token}",
        "package_name": f"Cobalt Distribution {token}",
        "package_slug": f"cobalt-dist-{token}",
        "version": f"2026.08.{int(token[-2:], 16) % 90 + 10}",
        "platform": "linux_amd64",
        "build_id": f"cobalt-approved-build-{token}",
        "base_branch": f"release/cobalt-{token}",
        "feature_branch": f"release/cobalt-{token}-publish",
        "protected_branch": f"work/cobalt-{token}-next",
        # Keep the human-readable version while retaining the full random
        # identity token; truncating it to a small date-like number caused
        # independently generated instances to collide.
        "release_tag": f"v2026.08.{release_number}-{token}",
        "protected_release_tag": (
            f"v2026.07.{protected_release_number}-{token}"
        ),
        "manifest_path": f"release/{token}/publication-manifest.json",
        "protected_file_path": f"docs/{token}/next-release.md",
        "branch_protection_rule": f"release/cobalt-{token}*",
        "release_title": f"Cobalt production release {token}",
        "release_body": f"Approved binary, checksum and SPDX publication {token}.",
        "milestone_title": f"Cobalt release milestone {token}",
        "target_issue_title": f"Publish the approved Cobalt bundle {token}",
        "protected_pull_title": f"Prepare Cobalt follow-up {token}",
        "protected_issue_title": f"Plan Cobalt maintenance {token}",
        "protected_release_title": f"Cobalt maintenance release {token}",
        "coordinator_consumer": f"cobalt-coordinator-{token}",
        "provenance_consumer": f"cobalt-provenance-{token}",
        "coordinator_target": "http://webhook-fault-gateway:8080/webhooks/events",
        "provenance_target": (
            "http://provenance-webhook-fault-gateway:8080/webhooks/events"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_instance(args.instance_id), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"created": True, "instance_id": args.instance_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
