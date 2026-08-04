from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .deployment_target_api import DeploymentTargetAPI
from .forgejo_api import ForgejoAPI
from .forgejo_promotion_evaluator import get_external_delivery
from .forgejo_promotion_instance import ForgejoPromotionInstanceSpec
from .forgejo_stack import ForgejoStack


@dataclass
class ForgejoPromotionReferenceAgent:
    forgejo: ForgejoAPI
    deployment: DeploymentTargetAPI
    stack: ForgejoStack
    instance: ForgejoPromotionInstanceSpec
    prefix: dict[str, Any]
    external_url: str = "http://127.0.0.1:9092"

    def __post_init__(self) -> None:
        self.trace: list[dict[str, Any]] = []

    def _record(self, tool: str, arguments: dict[str, Any], result: Any, *, kind: str) -> Any:
        self.trace.append(
            {
                "tool": tool,
                "arguments": arguments,
                "result": result,
                "kind": kind,
                "status": "success",
            }
        )
        return result

    def _wait(self, run_id: int, *, attempts: int = 120) -> dict[str, Any]:
        last: dict[str, Any] = {}
        for attempt in range(attempts):
            last = self._record(
                "get_action_run",
                {"run_id": run_id},
                self.forgejo.get_action_run(
                    self.instance.owner, self.instance.repository, run_id
                ),
                kind="read",
            )
            if last.get("status") in {"success", "failure", "cancelled", "skipped"}:
                return last
            if attempt + 1 < attempts:
                time.sleep(1)
        raise RuntimeError(f"Actions run {run_id} did not terminate: {last}")

    def _dispatch(self, inputs: dict[str, str] | None = None) -> dict[str, Any]:
        dispatched = self._record(
            "dispatch_workflow",
            {"workflow": self.instance.workflow_path, "ref": "main", "inputs": inputs or {}},
            self.forgejo.dispatch_workflow(
                self.instance.owner,
                self.instance.repository,
                workflow=self.instance.workflow_path,
                ref="main",
                inputs=inputs or None,
            ),
            kind="write",
        )
        return self._wait(int(dispatched["id"]))

    def _failure_diagnostics(self, run_id: int) -> dict[str, Any]:
        jobs = self._record(
            "list_action_run_jobs",
            {"run_id": run_id},
            self.forgejo.list_action_run_jobs(
                self.instance.owner, self.instance.repository, run_id
            ),
            kind="read",
        )
        diagnostics: list[dict[str, Any]] = []
        for job in jobs:
            job_id = int(job["id"])
            log = self._record(
                "get_action_job_logs",
                {"job_id": job_id},
                self.forgejo.get_action_job_logs(
                    self.instance.owner, self.instance.repository, job_id
                ),
                kind="read",
            )
            diagnostics.append(
                {
                    "id": job_id,
                    "name": job.get("name"),
                    "status": job.get("status"),
                    "steps": job.get("steps", []),
                    "log_tail": "\n".join(log.splitlines()[-80:]),
                }
            )
        return {"run_id": run_id, "jobs": diagnostics}

    def recover(self) -> tuple[dict[str, Any], ...]:
        spec = self.instance
        self._record(
            "get_branch",
            {"branch": "main"},
            self.forgejo.get_branch(spec.owner, spec.repository, "main"),
            kind="read",
        )
        for path in (
            spec.approval_manifest_path,
            spec.binary_path,
            spec.signature_path,
            spec.sbom_path,
            spec.provenance_path,
            spec.workflow_path,
        ):
            self._record(
                "get_repository_content",
                {"path": path, "ref": "main"},
                self.forgejo.get_repository_content(
                    spec.owner, spec.repository, path=path, ref="main"
                ),
                kind="read",
            )
        self._record(
            "list_issues",
            {},
            self.forgejo.list_issues(spec.owner, spec.repository),
            kind="read",
        )
        runs = self._record(
            "list_action_runs",
            {},
            self.forgejo.list_action_runs(spec.owner, spec.repository),
            kind="read",
        )
        state = self._record(
            "get_deployment_state", {}, self.deployment.state(), kind="read"
        )
        attestation = self._record(
            "get_external_attestation",
            {"key": spec.attestation_key},
            get_external_delivery(self.external_url, spec.attestation_key),
            kind="read",
        )
        artifact = next(
            (row for row in state["artifacts"] if row["version"] == spec.version), None
        )
        deployment = next(
            (
                row
                for row in state["deployments"]
                if row["environment"] == spec.production_environment
                and row["desired_version"] == spec.version
                and row["status"] == "deployed"
            ),
            None,
        )
        if not runs:
            run = self._dispatch()
        else:
            run = runs[0]
            if run.get("status") == "waiting":
                self.stack.start_action_runner()
                self._record("start_action_runner", {}, {"started": True}, kind="write")
                run = self._wait(int(run["id"]))
            elif run.get("status") == "failure":
                if artifact is not None and deployment is None:
                    run = self._dispatch({"resume_stage": "after_bundle"})
                elif deployment is not None and attestation is None:
                    run = self._dispatch({"resume_stage": "after_deployment"})
                else:
                    raise RuntimeError("failed promotion run lacks a safe resumable boundary")
            elif run.get("status") != "success":
                raise RuntimeError(f"unsupported Actions state: {run}")
        if run.get("status") != "success":
            diagnostics = self._failure_diagnostics(int(run["id"]))
            raise RuntimeError(
                "promotion recovery run did not succeed: "
                f"status={run.get('status')}; diagnostics={diagnostics}"
            )
        verified = self._record(
            "get_deployment_state", {}, self.deployment.state(), kind="read"
        )
        attestation = self._record(
            "get_external_attestation",
            {"key": spec.attestation_key},
            get_external_delivery(self.external_url, spec.attestation_key),
            kind="read",
        )
        if attestation is None or int(attestation.get("attempt_count", 0)) != 1:
            raise RuntimeError("transparency attestation is missing or duplicated")
        production = next(
            (
                row
                for row in verified["deployments"]
                if row["environment"] == spec.production_environment
            ),
            None,
        )
        if production is None or production.get("artifact_digest") != spec.artifact_digest:
            raise RuntimeError("production digest does not match the approval")
        releases = self._record(
            "list_releases",
            {},
            self.forgejo.list_releases(spec.owner, spec.repository),
            kind="read",
        )
        if not any(item.get("tag_name") == spec.release_tag for item in releases):
            self._record(
                "create_release",
                {"tag": spec.release_tag, "target": "main"},
                self.forgejo.create_release(
                    spec.owner,
                    spec.repository,
                    tag=spec.release_tag,
                    target="main",
                    title=f"Clinical alert router {spec.version}",
                    body=(
                        f"Production digest {spec.artifact_digest}; transparency "
                        f"attestation {spec.attestation_key}; Actions run {int(run['id'])}."
                    ),
                ),
                kind="write",
            )
        comments = self._record(
            "list_issue_comments",
            {"index": int(self.prefix["rollout_issue_index"])},
            self.forgejo.list_issue_comments(
                spec.owner, spec.repository, int(self.prefix["rollout_issue_index"])
            ),
            kind="read",
        )
        marker = f"{spec.version} {spec.artifact_digest} {spec.attestation_key}"
        if not any(marker in str(item.get("body", "")) for item in comments):
            self._record(
                "create_issue_comment",
                {"index": int(self.prefix["rollout_issue_index"]), "body": marker},
                self.forgejo.create_issue_comment(
                    spec.owner,
                    spec.repository,
                    int(self.prefix["rollout_issue_index"]),
                    body=f"Verified promotion: {marker}; Actions run {int(run['id'])}.",
                ),
                kind="write",
            )
        issues = self.forgejo.list_issues(spec.owner, spec.repository)
        rollout = next(
            (
                issue
                for issue in issues
                if int(issue.get("number", -1))
                == int(self.prefix["rollout_issue_index"])
            ),
            None,
        )
        if rollout is None:
            raise RuntimeError("rollout issue disappeared")
        if rollout.get("state") != "closed":
            self._record(
                "edit_issue",
                {"index": int(self.prefix["rollout_issue_index"]), "state": "closed"},
                self.forgejo.edit_issue(
                    spec.owner,
                    spec.repository,
                    int(self.prefix["rollout_issue_index"]),
                    state="closed",
                ),
                kind="write",
            )
        return tuple(self.trace)


__all__ = ["ForgejoPromotionReferenceAgent"]
