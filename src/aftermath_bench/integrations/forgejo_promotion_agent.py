from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from .deployment_target_api import DeploymentTargetAPI
from .forgejo_api import ForgejoAPI
from .forgejo_promotion_evaluator import (
    ForgejoPromotionEvaluator,
    get_external_delivery,
)
from .forgejo_promotion_instance import ForgejoPromotionInstanceSpec
from .forgejo_stack import ForgejoStack


class ForgejoPromotionEnvironment:
    """Ordinary cross-system tools exposed for promotion recovery."""

    TOOL_NAMES = (
        "get_branch",
        "get_repository_content",
        "list_issues",
        "list_issue_comments",
        "list_releases",
        "list_action_runs",
        "list_action_run_jobs",
        "list_action_run_artifacts",
        "get_deployment_state",
        "get_external_attestation",
        "dispatch_workflow",
        "start_action_runner",
        "create_release",
        "create_issue_comment",
        "edit_issue",
        "wait_for_action_run",
    )
    MUTATION_TOOLS = frozenset(
        {
            "dispatch_workflow",
            "start_action_runner",
            # Waiting is state advancing: an active runner can complete the
            # deployment and external publication while this call blocks.
            "wait_for_action_run",
            "create_release",
            "create_issue_comment",
            "edit_issue",
        }
    )

    def __init__(
        self,
        *,
        forgejo: ForgejoAPI,
        deployment: DeploymentTargetAPI,
        stack: ForgejoStack,
        instance: ForgejoPromotionInstanceSpec,
        prefix: dict[str, Any],
        variant: str,
        external_url: str = "http://127.0.0.1:9092",
    ) -> None:
        self.forgejo = forgejo
        self.deployment = deployment
        self.stack = stack
        self.instance = instance
        self.prefix = prefix
        self.variant = variant
        self.external_url = external_url
        self._events: list[dict[str, Any]] = []
        boundary_runs = self.forgejo.list_action_runs(
            self.instance.owner, self.instance.repository
        )
        terminal_failures = {"failure", "cancelled", "skipped"}
        # No owner means one must be created. A pending or successful owner is
        # preserved. If every existing owner terminated unsuccessfully, exactly
        # one resume owner is required. This is derived from the authoritative
        # boundary rather than from the hidden fault-variant label.
        if not boundary_runs:
            self.expected_action_run_count = 1
        elif all(
            str(run.get("status")) in terminal_failures for run in boundary_runs
        ):
            self.expected_action_run_count = len(boundary_runs) + 1
        else:
            self.expected_action_run_count = len(boundary_runs)

    def _record(
        self,
        tool: str,
        arguments: dict[str, Any],
        operation: Callable[[], Any],
    ) -> dict[str, Any]:
        try:
            value = operation()
            result = {"ok": True, "result": value}
        except Exception as error:  # noqa: BLE001 - tool errors are observations
            result = {
                "ok": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        self._events.append({"tool": tool, "arguments": arguments, "result": result})
        return result

    def _wait_for_action_run(self, run_id: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: dict[str, Any] = {}
        while True:
            last = self.forgejo.get_action_run(
                self.instance.owner, self.instance.repository, run_id
            )
            if last.get("status") in {
                "success",
                "failure",
                "cancelled",
                "skipped",
            }:
                return last
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Actions run {run_id} did not settle: {last}")
            time.sleep(0.5)

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        spec = self.instance
        owner = spec.owner
        repository = spec.repository
        operations: dict[str, Callable[[], Any]] = {
            "get_branch": lambda: self.forgejo.get_branch(
                owner, repository, str(kwargs.get("branch", "main"))
            ),
            "get_repository_content": lambda: self.forgejo.get_repository_content(
                owner,
                repository,
                path=str(kwargs["path"]),
                ref=str(kwargs.get("ref", "main")),
            ),
            "list_issues": lambda: self.forgejo.list_issues(owner, repository),
            "list_issue_comments": lambda: self.forgejo.list_issue_comments(
                owner, repository, int(kwargs["index"])
            ),
            "list_releases": lambda: self.forgejo.list_releases(owner, repository),
            "list_action_runs": lambda: self.forgejo.list_action_runs(
                owner, repository
            ),
            "list_action_run_jobs": lambda: self.forgejo.list_action_run_jobs(
                owner, repository, int(kwargs["run_id"])
            ),
            "list_action_run_artifacts": lambda: self.forgejo.list_action_run_artifacts(
                owner, repository, int(kwargs["run_id"])
            ),
            "get_deployment_state": self.deployment.state,
            "get_external_attestation": lambda: get_external_delivery(
                self.external_url, str(kwargs["key"])
            ),
            "dispatch_workflow": lambda: self.forgejo.dispatch_workflow(
                owner,
                repository,
                workflow=str(kwargs.get("workflow", spec.workflow_path)),
                ref=str(kwargs.get("ref", "main")),
                inputs=dict(kwargs.get("inputs") or {}),
            ),
            "start_action_runner": lambda: self._start_runner(),
            "create_release": lambda: self.forgejo.create_release(
                owner,
                repository,
                tag=str(kwargs["tag"]),
                target=str(kwargs.get("target", "main")),
                title=str(kwargs["title"]),
                body=str(kwargs["body"]),
            ),
            "create_issue_comment": lambda: self.forgejo.create_issue_comment(
                owner,
                repository,
                int(kwargs["index"]),
                body=str(kwargs["body"]),
            ),
            "edit_issue": lambda: self.forgejo.edit_issue(
                owner,
                repository,
                int(kwargs["index"]),
                state=str(kwargs["state"]),
            ),
            "wait_for_action_run": lambda: self._wait_for_action_run(
                int(kwargs["run_id"]), int(kwargs.get("timeout_seconds", 30))
            ),
        }
        if tool not in operations:
            raise KeyError(f"unknown Forgejo promotion tool: {tool}")
        return self._record(tool, dict(kwargs), operations[tool])

    def _start_runner(self) -> dict[str, bool]:
        self.stack.start_action_runner()
        return {"started": True}

    def snapshot(self) -> dict[str, Any]:
        evaluation = ForgejoPromotionEvaluator(
            forgejo=self.forgejo,
            deployment=self.deployment,
            instance=self.instance,
            prefix=self.prefix,
            external_url=self.external_url,
        ).evaluate(
            variant=self.variant,
            expected_run_count=self.expected_action_run_count,
        )
        return {"evaluation": evaluation, **evaluation["final_evidence"]}

    def event_log(self) -> list[dict[str, Any]]:
        return list(self._events)


__all__ = ["ForgejoPromotionEnvironment"]
