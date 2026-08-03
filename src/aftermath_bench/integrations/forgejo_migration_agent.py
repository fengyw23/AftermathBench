from __future__ import annotations

import base64
import hashlib
import time
from collections.abc import Callable
from typing import Any

from .deployment_target_api import DeploymentTargetAPI
from .forgejo_api import ForgejoAPI
from .forgejo_migration_evaluator import ForgejoMigrationEvaluator
from .forgejo_migration_instance import ForgejoMigrationInstanceSpec
from .forgejo_stack import ForgejoStack


class ForgejoMigrationEnvironment:
    """Ordinary Forgejo and deployment-target tools for model evaluation."""

    MUTATION_TOOLS = frozenset(
        {
            "dispatch_workflow",
            "start_action_runner",
            "create_release",
            "create_issue_comment",
            "set_issue_state",
            "set_milestone_state",
        }
    )

    def __init__(
        self,
        *,
        forgejo: ForgejoAPI,
        deployment: DeploymentTargetAPI,
        stack: ForgejoStack,
        instance: ForgejoMigrationInstanceSpec,
        prefix: dict[str, Any],
        variant: str,
    ) -> None:
        self.forgejo = forgejo
        self.deployment = deployment
        self.stack = stack
        self.instance = instance
        self.prefix = prefix
        self.variant = variant
        self._events: list[dict[str, Any]] = []

    def _record(
        self,
        tool: str,
        arguments: dict[str, Any],
        operation: Callable[[], Any],
    ) -> dict[str, Any]:
        try:
            value = operation()
            result = {"ok": True, "result": value}
        except Exception as error:  # noqa: BLE001 - tool failures are evidence
            result = {
                "ok": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        self._events.append(
            {"tool": tool, "arguments": dict(arguments), "result": result}
        )
        return result

    @property
    def owner(self) -> str:
        return self.instance.owner

    @property
    def repository(self) -> str:
        return self.instance.repository

    def _repository_file(self, path: str, ref: str) -> dict[str, Any]:
        document = self.forgejo.get_repository_content(
            self.owner,
            self.repository,
            path=path,
            ref=ref,
        )
        encoded = document.get("content")
        if not isinstance(encoded, str):
            raise TypeError("Forgejo repository file has no base64 content")
        content = base64.b64decode(encoded.replace("\n", ""), validate=True)
        return {
            "path": path,
            "ref": ref,
            "repository_sha": document.get("sha"),
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "content": content.decode("utf-8", errors="replace"),
        }

    def _wait_for_action_run(
        self,
        run_id: int,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while True:
            run = self.forgejo.get_action_run(self.owner, self.repository, run_id)
            if run.get("status") in {
                "success",
                "failure",
                "cancelled",
                "skipped",
            }:
                return run
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Actions run {run_id} did not reach a terminal state"
                )
            time.sleep(0.5)

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        owner = self.owner
        repository = self.repository
        operations: dict[str, Callable[[], Any]] = {
            "get_branch": lambda: self.forgejo.get_branch(
                owner, repository, str(kwargs["branch"])
            ),
            "get_repository_file": lambda: self._repository_file(
                str(kwargs["path"]), str(kwargs["ref"])
            ),
            "list_issues": lambda: self.forgejo.list_issues(owner, repository),
            "get_issue": lambda: self.forgejo.get(
                f"/repos/{owner}/{repository}/issues/{int(kwargs['index'])}"
            ),
            "get_milestone": lambda: self.forgejo.get_milestone(
                owner, repository, int(kwargs["milestone_id"])
            ),
            "list_action_runs": lambda: self.forgejo.list_action_runs(
                owner, repository
            ),
            "get_action_run": lambda: self.forgejo.get_action_run(
                owner, repository, int(kwargs["run_id"])
            ),
            "list_action_run_jobs": lambda: self.forgejo.list_action_run_jobs(
                owner, repository, int(kwargs["run_id"])
            ),
            "get_deployment_state": self.deployment.state,
            "list_releases": lambda: self.forgejo.list_releases(owner, repository),
            "list_issue_comments": lambda: self.forgejo.list_issue_comments(
                owner, repository, int(kwargs["index"])
            ),
            "dispatch_workflow": lambda: self.forgejo.dispatch_workflow(
                owner,
                repository,
                workflow=str(kwargs["workflow"]),
                ref=str(kwargs["ref"]),
                inputs={
                    str(key): str(value)
                    for key, value in dict(kwargs.get("inputs") or {}).items()
                },
            ),
            "start_action_runner": lambda: (
                self.stack.start_action_runner() or {"started": True}
            ),
            "wait_for_action_run": lambda: self._wait_for_action_run(
                int(kwargs["run_id"]), int(kwargs.get("timeout_seconds", 30))
            ),
            "create_release": lambda: self.forgejo.create_release(
                owner,
                repository,
                tag=str(kwargs["tag"]),
                target=str(kwargs["target"]),
                title=str(kwargs["title"]),
                body=str(kwargs["body"]),
            ),
            "create_issue_comment": lambda: self.forgejo.create_issue_comment(
                owner,
                repository,
                int(kwargs["index"]),
                body=str(kwargs["body"]),
            ),
            "set_issue_state": lambda: self.forgejo.edit_issue(
                owner,
                repository,
                int(kwargs["index"]),
                state=str(kwargs["state"]),
            ),
            "set_milestone_state": lambda: self.forgejo.edit_milestone(
                owner,
                repository,
                int(kwargs["milestone_id"]),
                state=str(kwargs["state"]),
            ),
        }
        if tool not in operations:
            raise KeyError(f"unknown Forgejo migration tool: {tool}")
        return self._record(tool, dict(kwargs), operations[tool])

    def event_log(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._events)

    def snapshot(self) -> dict[str, Any]:
        evaluation = ForgejoMigrationEvaluator(
            forgejo=self.forgejo,
            deployment=self.deployment,
            instance=self.instance,
            prefix=self.prefix,
        ).evaluate(variant=self.variant)
        return {
            **evaluation["final_evidence"],
            "_deterministic_evaluation": {
                key: value
                for key, value in evaluation.items()
                if key != "final_evidence"
            },
        }


__all__ = ["ForgejoMigrationEnvironment"]
