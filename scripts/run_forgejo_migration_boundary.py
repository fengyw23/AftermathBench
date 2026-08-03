from __future__ import annotations

import argparse
import http.client
import json
import time
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_migration_faults import (
    FORGEJO_MIGRATION_VARIANTS,
    ForgejoMigrationFaultController,
)
from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)
from aftermath_bench.integrations.forgejo_stack import ForgejoStack
from aftermath_bench.schema import repository_root


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def _wait_run(
    api: ForgejoAPI,
    instance: ForgejoMigrationInstanceSpec,
    expected_status: str,
    *,
    attempts: int = 90,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(attempts):
        runs = api.list_action_runs(
            instance.owner,
            instance.repository,
        )
        if runs:
            last = runs[0]
            if last.get("status") == expected_status:
                return last
        if attempt + 1 < attempts:
            time.sleep(1)
    raise RuntimeError(f"Actions run did not reach {expected_status!r}: {last}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize one native Forgejo migration failure boundary."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--variant", choices=FORGEJO_MIGRATION_VARIANTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-url", default="http://127.0.0.1:9095")
    args = parser.parse_args()
    credentials = _read(args.credentials)
    instance = ForgejoMigrationInstanceSpec.from_path(args.instance_spec)
    forgejo = ForgejoAPI(
        base_url=str(credentials["base_url"]),
        token=str(credentials["token"]),
    )
    deployment = DeploymentTargetAPI(args.deployment_url)
    runtime = repository_root() / "runtimes" / "forgejo"
    stack = ForgejoStack(compose_file=runtime / "compose.yaml")
    faults = ForgejoMigrationFaultController()
    specification = faults.arm(args.variant)
    if not specification.runner_enabled:
        stack.run("stop", "runner-daemon")
    surface_error = None
    try:
        forgejo.dispatch_workflow(
            instance.owner,
            instance.repository,
            workflow=instance.workflow_path,
            ref="main",
        )
        raise RuntimeError("ambiguous dispatch unexpectedly returned success")
    except (
        ConnectionError,
        ConnectionResetError,
        http.client.RemoteDisconnected,
        TimeoutError,
        OSError,
    ) as error:
        surface_error = type(error).__name__
    finally:
        faults.disarm_api()

    run: dict[str, Any] | None = None
    jobs: list[dict[str, Any]] = []
    if specification.expected_run_status is not None:
        run = _wait_run(forgejo, instance, specification.expected_run_status)
        jobs = forgejo.list_action_run_jobs(
            instance.owner, instance.repository, int(run["id"])
        )
    else:
        runs = forgejo.list_action_runs(
            instance.owner,
            instance.repository,
        )
        if runs:
            raise RuntimeError(f"suppressed dispatch created an Actions run: {runs}")
    faults.disarm_deployment()
    state = deployment.state()
    target_migrations = [
        row
        for row in state["migrations"]
        if row["migration_id"] == instance.migration_id
    ]
    target_deployments = [
        row
        for row in state["deployments"]
        if row["environment"] == instance.production_environment
        and row["desired_version"] == instance.version
    ]
    expected_effect = {
        "dispatch_request_not_reached": (0, 0),
        "workflow_queued_runner_unavailable": (0, 0),
        "migration_applied_workflow_failed": (1, 0),
        "workflow_completed_dispatch_response_lost": (1, 1),
    }[args.variant]
    checks = {
        "surface_error_observed": surface_error is not None,
        "native_run_presence_matches": (run is not None)
        is (specification.expected_run_status is not None),
        "native_run_status_matches": run is None
        or run.get("status") == specification.expected_run_status,
        "migration_effect_matches": len(target_migrations) == expected_effect[0],
        "deployment_effect_matches": len(target_deployments) == expected_effect[1],
    }
    payload = {
        "schema_version": "1.0",
        "scenario_id": instance.scenario_id,
        "instance_spec_sha256": instance.sha256,
        "variant": args.variant,
        "surface_result": {
            "ok": False,
            "error": "connection closed before workflow dispatch was acknowledged",
            "observed_exception": surface_error,
        },
        "visible_failure": {
            "ok": False,
            "error": "connection closed before workflow dispatch was acknowledged",
            "observed_exception": surface_error,
        },
        "runner_enabled": specification.runner_enabled,
        "action_run": run,
        "action_jobs": jobs,
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
    print(json.dumps({"variant": args.variant, "passed": payload["passed"]}))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
