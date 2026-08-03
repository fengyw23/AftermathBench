from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .deployment_target_api import DeploymentTargetAPI
from .forgejo_api import ForgejoAPI
from .forgejo_migration_instance import ForgejoMigrationInstanceSpec
from .forgejo_stack import ForgejoStack


@dataclass
class ForgejoMigrationReferenceAgent:
    forgejo: ForgejoAPI
    deployment: DeploymentTargetAPI
    stack: ForgejoStack
    instance: ForgejoMigrationInstanceSpec
    prefix: dict[str, Any]

    def __post_init__(self) -> None:
        self.trace: list[dict[str, Any]] = []

    def _record(
        self,
        tool: str,
        arguments: dict[str, Any],
        result: Any,
        *,
        kind: str,
    ) -> Any:
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

    def _wait(self, run_id: int, *, attempts: int = 90) -> dict[str, Any]:
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
            if last.get("status") in {
                "success",
                "failure",
                "cancelled",
                "skipped",
            }:
                return last
            if attempt + 1 < attempts:
                time.sleep(1)
        raise RuntimeError(f"Actions run {run_id} did not terminate: {last}")

    def recover(self) -> tuple[dict[str, Any], ...]:
        spec = self.instance
        runs = self._record(
            "list_action_runs",
            {},
            self.forgejo.list_action_runs(spec.owner, spec.repository),
            kind="read",
        )
        target_state = self._record(
            "get_deployment_state",
            {},
            self.deployment.state(),
            kind="read",
        )
        target_migration = next(
            (
                row
                for row in target_state["migrations"]
                if row["migration_id"] == spec.migration_id
            ),
            None,
        )
        if not runs:
            dispatched = self._record(
                "dispatch_workflow",
                {"workflow": spec.workflow_path, "ref": "main", "inputs": {}},
                self.forgejo.dispatch_workflow(
                    spec.owner,
                    spec.repository,
                    workflow=spec.workflow_path,
                    ref="main",
                ),
                kind="write",
            )
            run = self._wait(int(dispatched["id"]))
        else:
            run = runs[0]
            status = str(run.get("status"))
            if status == "waiting":
                self.stack.start_action_runner()
                self._record(
                    "start_action_runner",
                    {},
                    {"started": True},
                    kind="write",
                )
                run = self._wait(int(run["id"]))
            elif status == "failure":
                if target_migration is None:
                    raise RuntimeError(
                        "failed run lacks the migration evidence required for safe resume"
                    )
                dispatched = self._record(
                    "dispatch_workflow",
                    {
                        "workflow": spec.workflow_path,
                        "ref": "main",
                        "inputs": {"resume_after_migration": "true"},
                    },
                    self.forgejo.dispatch_workflow(
                        spec.owner,
                        spec.repository,
                        workflow=spec.workflow_path,
                        ref="main",
                        inputs={"resume_after_migration": "true"},
                    ),
                    kind="write",
                )
                run = self._wait(int(dispatched["id"]))
            elif status != "success":
                raise RuntimeError(f"unsupported Actions state: {run}")
        if run.get("status") != "success":
            raise RuntimeError(f"recovery workflow did not succeed: {run}")

        verified = self._record(
            "get_deployment_state",
            {},
            self.deployment.state(),
            kind="read",
        )
        production = next(
            (
                row
                for row in verified["deployments"]
                if row["environment"] == spec.production_environment
            ),
            None,
        )
        replicas = [
            row
            for row in verified["replicas"]
            if row["environment"] == spec.production_environment
        ]
        if (
            production is None
            or production["desired_version"] != spec.version
            or production["status"] != "deployed"
            or len(replicas) != 2
            or any(row["status"] != "ready" for row in replicas)
        ):
            raise RuntimeError("production was not authoritatively verified")

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
                    title=f"Customer API {spec.version}",
                    body=(
                        f"Verified production deployment of {spec.artifact_digest}; "
                        f"Actions run {int(run['id'])}."
                    ),
                ),
                kind="write",
            )
        comments = self._record(
            "list_issue_comments",
            {"index": int(self.prefix["change_issue_index"])},
            self.forgejo.list_issue_comments(
                spec.owner,
                spec.repository,
                int(self.prefix["change_issue_index"]),
            ),
            kind="read",
        )
        marker = f"Deployment verification: {spec.version} {spec.artifact_digest}"
        if not any(marker in str(item.get("body", "")) for item in comments):
            self._record(
                "create_issue_comment",
                {"index": int(self.prefix["change_issue_index"]), "body": marker},
                self.forgejo.create_issue_comment(
                    spec.owner,
                    spec.repository,
                    int(self.prefix["change_issue_index"]),
                    body=f"{marker}; Actions run {int(run['id'])} succeeded.",
                ),
                kind="write",
            )
        self._record(
            "edit_issue",
            {"index": int(self.prefix["change_issue_index"]), "state": "closed"},
            self.forgejo.edit_issue(
                spec.owner,
                spec.repository,
                int(self.prefix["change_issue_index"]),
                state="closed",
            ),
            kind="write",
        )
        self._record(
            "edit_milestone",
            {"milestone_id": int(self.prefix["milestone_id"]), "state": "closed"},
            self.forgejo.edit_milestone(
                spec.owner,
                spec.repository,
                int(self.prefix["milestone_id"]),
                state="closed",
            ),
            kind="write",
        )
        return tuple(self.trace)
