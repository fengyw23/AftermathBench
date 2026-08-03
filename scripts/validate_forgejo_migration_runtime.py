from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute and verify the native Forgejo migration workflow."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--deployment-url", default="http://127.0.0.1:9095"
    )
    parser.add_argument("--attempts", type=int, default=90)
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    instance = ForgejoMigrationInstanceSpec.from_path(args.instance_spec)
    forgejo = ForgejoAPI(
        base_url=str(credentials["base_url"]),
        token=str(credentials["token"]),
    )
    target = DeploymentTargetAPI(args.deployment_url)
    dispatched = forgejo.dispatch_workflow(
        instance.owner,
        instance.repository,
        workflow=instance.workflow_path,
        ref="main",
    )
    run_id = int(dispatched["id"])
    run = {}
    terminal_statuses = {"success", "failure", "cancelled", "skipped"}
    for attempt in range(args.attempts):
        run = forgejo.get_action_run(
            instance.owner, instance.repository, run_id
        )
        if run.get("status") in terminal_statuses:
            break
        if attempt + 1 < args.attempts:
            time.sleep(1)
    jobs = forgejo.list_action_run_jobs(
        instance.owner, instance.repository, run_id
    )
    state = target.state()
    migrations = [
        row
        for row in state["migrations"]
        if row["migration_id"] == instance.migration_id
    ]
    artifacts = [
        row for row in state["artifacts"] if row["version"] == instance.version
    ]
    deployments = [
        row
        for row in state["deployments"]
        if row["environment"] == instance.production_environment
    ]
    replicas = [
        row
        for row in state["replicas"]
        if row["environment"] == instance.production_environment
    ]
    audits = [
        row
        for row in state["audit_events"]
        if row["event_key"]
        == f"verify-{instance.production_environment}-{instance.version}"
    ]
    checks = {
        "run_reached_terminal_status": run.get("status") in terminal_statuses,
        "run_succeeded": run.get("status") == "success",
        "job_visible": bool(jobs),
        "migration_applied_once": len(migrations) == 1
        and migrations[0]["attempt_count"] == 1,
        "artifact_registered_once": len(artifacts) == 1
        and artifacts[0]["attempt_count"] == 1,
        "production_deployed": len(deployments) == 1
        and deployments[0]["status"] == "deployed",
        "two_matching_replicas": len(replicas) == 2
        and all(
            row["version"] == instance.version
            and row["artifact_digest"] == instance.artifact_digest
            and row["status"] == "ready"
            for row in replicas
        ),
        "audit_recorded_once": len(audits) == 1
        and audits[0]["attempt_count"] == 1,
    }
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "run": run,
        "jobs": jobs,
        "deployment_state": state,
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"run_id": run_id, "passed": payload["passed"], "checks": checks}))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
