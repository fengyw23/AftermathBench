from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .deployment_target_api import DeploymentTargetAPI
from .forgejo_api import ForgejoAPI
from .forgejo_migration_instance import ForgejoMigrationInstanceSpec
from .forgejo_stack import ForgejoStack


FORGEJO_MIGRATION_BASELINES = (
    "no_op",
    "assume_effect_complete",
    "blind_redispatch",
    "always_skip_migration",
    "always_restart_runner",
    "close_tracking_only",
)


@dataclass
class ForgejoMigrationBaselineAgent:
    forgejo: ForgejoAPI
    deployment: DeploymentTargetAPI
    stack: ForgejoStack
    instance: ForgejoMigrationInstanceSpec
    prefix: dict[str, Any]

    def __post_init__(self) -> None:
        self.trace: list[dict[str, Any]] = []

    def _record(
        self, tool: str, arguments: dict[str, Any], result: Any, *, kind: str
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
        return last

    def _dispatch(self, *, skip_migration: bool) -> None:
        self.stack.start_action_runner()
        self._record(
            "start_action_runner", {}, {"started": True}, kind="write"
        )
        inputs = (
            {"resume_after_migration": "true"} if skip_migration else {}
        )
        dispatched = self._record(
            "dispatch_workflow",
            {"inputs": inputs},
            self.forgejo.dispatch_workflow(
                self.instance.owner,
                self.instance.repository,
                workflow=self.instance.workflow_path,
                ref="main",
                inputs=inputs,
            ),
            kind="write",
        )
        self._wait(int(dispatched["id"]))

    def _finalize_if_deployed(self) -> None:
        spec = self.instance
        state = self._record(
            "get_deployment_state",
            {},
            self.deployment.state(),
            kind="read",
        )
        deployed = any(
            row["environment"] == spec.production_environment
            and row["desired_version"] == spec.version
            and row["status"] == "deployed"
            for row in state["deployments"]
        )
        if not deployed:
            return
        releases = self.forgejo.list_releases(spec.owner, spec.repository)
        if not any(item.get("tag_name") == spec.release_tag for item in releases):
            self._record(
                "create_release",
                {"tag": spec.release_tag},
                self.forgejo.create_release(
                    spec.owner,
                    spec.repository,
                    tag=spec.release_tag,
                    target="main",
                    title=f"Customer API {spec.version}",
                    body=f"Deployment of {spec.artifact_digest} recorded.",
                ),
                kind="write",
            )
        marker = f"Deployment verification: {spec.version} {spec.artifact_digest}"
        comments = self.forgejo.list_issue_comments(
            spec.owner,
            spec.repository,
            int(self.prefix["change_issue_index"]),
        )
        if not any(marker in str(item.get("body", "")) for item in comments):
            self._record(
                "create_issue_comment",
                {"body": marker},
                self.forgejo.create_issue_comment(
                    spec.owner,
                    spec.repository,
                    int(self.prefix["change_issue_index"]),
                    body=marker,
                ),
                kind="write",
            )
        self._record(
            "edit_issue",
            {"state": "closed"},
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
            {"state": "closed"},
            self.forgejo.edit_milestone(
                spec.owner,
                spec.repository,
                int(self.prefix["milestone_id"]),
                state="closed",
            ),
            kind="write",
        )

    def run(self, policy: str) -> tuple[dict[str, Any], ...]:
        if policy not in FORGEJO_MIGRATION_BASELINES:
            raise ValueError(f"unknown Forgejo migration baseline: {policy}")
        if policy == "no_op":
            return tuple(self.trace)
        if policy == "blind_redispatch":
            self._dispatch(skip_migration=False)
        elif policy == "always_skip_migration":
            self._dispatch(skip_migration=True)
        elif policy == "always_restart_runner":
            self.stack.start_action_runner()
            self._record(
                "start_action_runner", {}, {"started": True}, kind="write"
            )
            runs = self.forgejo.list_action_runs(
                self.instance.owner, self.instance.repository
            )
            if runs:
                self._wait(int(runs[0]["id"]))
        elif policy == "close_tracking_only":
            self._record(
                "edit_issue",
                {"state": "closed"},
                self.forgejo.edit_issue(
                    self.instance.owner,
                    self.instance.repository,
                    int(self.prefix["change_issue_index"]),
                    state="closed",
                ),
                kind="write",
            )
            return tuple(self.trace)
        self._finalize_if_deployed()
        return tuple(self.trace)
