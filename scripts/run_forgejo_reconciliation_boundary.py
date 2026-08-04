from __future__ import annotations

import argparse
import http.client
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_promotion_faults import (
    ForgejoPromotionFaultController,
)
from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
)
from aftermath_bench.integrations.forgejo_reconciliation_faults import (
    FORGEJO_RECONCILIATION_VARIANTS,
)
from aftermath_bench.integrations.forgejo_reconciliation_recovery import (
    collect_reconciliation_state,
    project_reconciliation_obligations,
)


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object in {path}")
    return payload


def _wait_new_run(
    api: ForgejoAPI,
    instance: ForgejoPromotionInstanceSpec,
    before: set[int],
    *,
    attempts: int = 120,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    terminal = {"success", "failure", "cancelled", "skipped"}
    for attempt in range(attempts):
        runs = api.list_action_runs(instance.owner, instance.repository)
        created = [row for row in runs if int(row["id"]) not in before]
        if len(created) == 1:
            last = created[0]
            if str(last.get("status")) in terminal:
                return last
        elif len(created) > 1:
            raise RuntimeError("ambiguous dispatch created multiple Actions owners")
        if attempt + 1 < attempts:
            time.sleep(1)
    raise RuntimeError(f"Actions owner did not settle: {last}")


def _dispatch_ambiguously(
    *,
    api: ForgejoAPI,
    instance: ForgejoPromotionInstanceSpec,
    faults: ForgejoPromotionFaultController,
    inputs: dict[str, str],
    mode: str = "drop_response",
) -> tuple[str, dict[str, Any] | None]:
    before = {
        int(row["id"])
        for row in api.list_action_runs(instance.owner, instance.repository)
    }
    faults.arm_dispatch_transport(mode)
    observed_exception = ""
    try:
        api.dispatch_workflow(
            instance.owner,
            instance.repository,
            workflow=instance.workflow_path,
            ref="main",
            inputs=inputs,
        )
        raise RuntimeError("faulted reconciliation dispatch returned normally")
    except (
        ConnectionError,
        ConnectionResetError,
        http.client.RemoteDisconnected,
        TimeoutError,
        OSError,
    ) as error:
        observed_exception = type(error).__name__
    finally:
        faults.disarm_api()
    if mode == "suppress_request":
        runs = api.list_action_runs(instance.owner, instance.repository)
        if any(int(row["id"]) not in before for row in runs):
            raise RuntimeError("suppressed Actions dispatch reached Forgejo")
        return observed_exception, None
    return observed_exception, _wait_new_run(api, instance, before)


def _post_attestation(url: str, instance: ForgejoPromotionInstanceSpec) -> None:
    payload = {
        "idempotency_key": instance.attestation_key,
        "version": instance.version,
        "artifact_digest": instance.artifact_digest,
        "signer_identity": instance.signer_identity,
        "environment": instance.production_environment,
    }
    request = urllib.request.Request(
        f"{url.rstrip('/')}/webhooks/events",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        response.read()


def _finalize_metadata(
    api: ForgejoAPI,
    instance: ForgejoPromotionInstanceSpec,
    prefix: dict[str, Any],
) -> None:
    api.create_release(
        instance.owner,
        instance.repository,
        tag=instance.release_tag,
        target="main",
        title=f"{instance.repository} {instance.version}",
        body=(
            f"Production digest {instance.artifact_digest}; transparency "
            f"attestation {instance.attestation_key}."
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
        description="Materialize one native independent-gap Forgejo boundary."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument(
        "--variant", choices=tuple(FORGEJO_RECONCILIATION_VARIANTS), required=True
    )
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
    faults = ForgejoPromotionFaultController()
    variant = args.variant

    if variant == "actions_bundle_missing":
        observed_exception, run = _dispatch_ambiguously(
            api=api,
            instance=instance,
            faults=faults,
            inputs={},
            mode="suppress_request",
        )
        deployment.register_artifact(
            version=instance.version,
            digest=instance.artifact_digest,
            source_commit=instance.approved_commit,
        )
        deployment.request_artifact_deployment(
            environment=instance.production_environment,
            version=instance.version,
            artifact_digest=instance.artifact_digest,
        )
        deployment.run_workers()
        _post_attestation(args.external_url, instance)
        _finalize_metadata(api, instance, prefix)
    else:
        inputs = {
            "artifact_registry_missing": {
                "resume_stage": "start",
                "stop_after": "artifact",
            },
            "production_deployment_missing": {
                "resume_stage": "start",
                "stop_after": "bundle",
            },
            "external_attestation_missing": {
                "resume_stage": "start",
                "stop_after": "deployment",
            },
            "release_metadata_missing": {
                "resume_stage": "start",
                "stop_after": "none",
            },
            "all_effects_valid_response_lost": {
                "resume_stage": "start",
                "stop_after": "none",
            },
        }[variant]
        observed_exception, run = _dispatch_ambiguously(
            api=api,
            instance=instance,
            faults=faults,
            inputs=inputs,
        )
        if variant == "artifact_registry_missing":
            deployment.register_artifact(
                version=instance.version,
                digest=instance.artifact_digest,
                source_commit=instance.approved_commit,
            )
            deployment.request_artifact_deployment(
                environment=instance.production_environment,
                version=instance.version,
                artifact_digest=instance.artifact_digest,
            )
            deployment.run_workers()
            _post_attestation(args.external_url, instance)
            _finalize_metadata(api, instance, prefix)
            deleted = deployment.delete_artifact_for_fault_injection(instance.version)
            if not deleted.get("deleted"):
                raise RuntimeError("registry-gap injection removed no artifact")
        elif variant == "production_deployment_missing":
            _post_attestation(args.external_url, instance)
            _finalize_metadata(api, instance, prefix)
        elif variant in {
            "external_attestation_missing",
            "all_effects_valid_response_lost",
        }:
            _finalize_metadata(api, instance, prefix)

    state = collect_reconciliation_state(
        forgejo=api,
        deployment=deployment,
        instance=instance,
        prefix=prefix,
        external_url=args.external_url,
    )
    projection = project_reconciliation_obligations(
        state, instance=instance, prefix=prefix
    )
    expected_gap = FORGEJO_RECONCILIATION_VARIANTS[variant].missing_obligation
    observed_gaps = [name for name, valid in projection.items() if not valid]
    checks = {
        "real_transport_error_observed": bool(observed_exception),
        "exactly_expected_obligation_missing": observed_gaps
        == ([] if expected_gap is None else [expected_gap]),
    }
    payload = {
        "schema_version": "0.1",
        "artifact_type": "forgejo_cross_system_reconciliation_boundary",
        "scenario_id": f"{instance.scenario_id}--reconciliation",
        "variant": variant,
        "surface_result": {
            "ok": False,
            "error": "connection closed before reconciliation was acknowledged",
            "observed_exception": observed_exception,
        },
        "action_run": run,
        "dimension_projection": projection,
        "boundary_state": state,
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps({"variant": variant, "checks": checks}, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
