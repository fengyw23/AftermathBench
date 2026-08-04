from __future__ import annotations

import argparse
import http.client
import json
import time
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_promotion_evaluator import (
    get_external_delivery,
)
from aftermath_bench.integrations.forgejo_promotion_faults import (
    FORGEJO_PROMOTION_VARIANTS,
    ForgejoPromotionFaultController,
)
from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
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
    instance: ForgejoPromotionInstanceSpec,
    expected_status: str,
    *,
    attempts: int = 120,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(attempts):
        runs = api.list_action_runs(instance.owner, instance.repository)
        if runs:
            last = runs[0]
            if last.get("status") == expected_status:
                return last
        if attempt + 1 < attempts:
            time.sleep(1)
    raise RuntimeError(f"Actions run did not reach {expected_status!r}: {last}")


def _finalize_metadata(
    api: ForgejoAPI,
    instance: ForgejoPromotionInstanceSpec,
    prefix: dict[str, Any],
    run: dict[str, Any],
) -> None:
    api.create_release(
        instance.owner,
        instance.repository,
        tag=instance.release_tag,
        target="main",
        title=f"Clinical alert router {instance.version}",
        body=(
            f"Production digest {instance.artifact_digest}; transparency "
            f"attestation {instance.attestation_key}; Actions run {int(run['id'])}."
        ),
    )
    api.create_issue_comment(
        instance.owner,
        instance.repository,
        int(prefix["rollout_issue_index"]),
        body=(
            f"Verified promotion: {instance.version} {instance.artifact_digest} "
            f"{instance.attestation_key}; Actions run {int(run['id'])}."
        ),
    )
    api.edit_issue(
        instance.owner,
        instance.repository,
        int(prefix["rollout_issue_index"]),
        state="closed",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Materialize one native Forgejo promotion failure boundary."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--variant", choices=FORGEJO_PROMOTION_VARIANTS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-url", default="http://127.0.0.1:9095")
    parser.add_argument("--external-url", default="http://127.0.0.1:9092")
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    instance = ForgejoPromotionInstanceSpec.from_path(args.instance_spec)
    api = ForgejoAPI(
        base_url=str(credentials["base_url"]), token=str(credentials["token"])
    )
    deployment = DeploymentTargetAPI(args.deployment_url)
    stack = ForgejoStack(
        compose_file=repository_root() / "runtimes" / "forgejo" / "compose.yaml"
    )
    faults = ForgejoPromotionFaultController()
    specification = faults.arm(args.variant)
    if not specification.runner_enabled:
        stack.run("stop", "runner-daemon")
    surface_error = None
    try:
        api.dispatch_workflow(
            instance.owner,
            instance.repository,
            workflow=instance.workflow_path,
            ref="main",
            inputs=specification.workflow_inputs,
        )
        raise RuntimeError("ambiguous promotion unexpectedly returned success")
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
    action_artifacts: list[dict[str, Any]] = []
    if specification.expected_run_status is not None:
        run = _wait_run(api, instance, specification.expected_run_status)
        jobs = api.list_action_run_jobs(instance.owner, instance.repository, int(run["id"]))
        action_artifacts = api.list_action_run_artifacts(
            instance.owner, instance.repository, int(run["id"])
        )
    else:
        runs = api.list_action_runs(instance.owner, instance.repository)
        if runs:
            raise RuntimeError(f"suppressed dispatch created an Actions run: {runs}")
    if specification.finalize_release_metadata:
        if run is None:
            raise RuntimeError("completed promotion has no native Actions owner")
        _finalize_metadata(api, instance, prefix, run)
    state = deployment.state()
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
    attestation = get_external_delivery(args.external_url, instance.attestation_key)
    releases = api.list_releases(instance.owner, instance.repository)
    issues = api.list_issues(instance.owner, instance.repository)
    rollout = next(
        (
            item
            for item in issues
            if int(item.get("number", -1)) == int(prefix["rollout_issue_index"])
        ),
        None,
    )
    expected = {
        "dispatch_request_not_reached": (0, 0, 0, 0),
        "workflow_queued_runner_unavailable": (0, 0, 0, 0),
        "signed_bundle_completed_deployment_missing": (1, 0, 0, 0),
        "deployment_completed_attestation_missing": (1, 1, 0, 0),
        "attestation_accepted_release_metadata_missing": (1, 1, 1, 0),
        "promotion_completed_response_lost": (1, 1, 1, 1),
    }[args.variant]
    observed = (
        len(target_artifacts),
        len(target_deployments),
        int(attestation is not None),
        int(
            any(release.get("tag_name") == instance.release_tag for release in releases)
            and rollout is not None
            and rollout.get("state") == "closed"
        ),
    )
    checks = {
        "surface_error_observed": surface_error is not None,
        "native_run_presence_matches": (run is not None)
        is (specification.expected_run_status is not None),
        "native_run_status_matches": run is None
        or run.get("status") == specification.expected_run_status,
        "cross_system_effects_match": observed == expected,
        "native_artifact_matches_bundle_state": bool(action_artifacts)
        is bool(expected[0]),
    }
    payload = {
        "schema_version": "1.0",
        "scenario_id": instance.scenario_id,
        "instance_spec_sha256": instance.sha256,
        "variant": args.variant,
        "surface_result": {
            "ok": False,
            "error": "connection closed before promotion was acknowledged",
            "observed_exception": surface_error,
        },
        "runner_enabled": specification.runner_enabled,
        "action_run": run,
        "action_jobs": jobs,
        "action_artifacts": action_artifacts,
        "deployment_state": state,
        "external_attestation": attestation,
        "releases": releases,
        "issues": issues,
        "observed_stage_vector": observed,
        "expected_stage_vector": expected,
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
