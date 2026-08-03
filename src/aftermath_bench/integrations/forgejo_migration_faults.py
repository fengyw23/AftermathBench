from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .forgejo_faults import _json_request


@dataclass(frozen=True)
class MigrationBoundaryVariant:
    api_mode: str
    deployment_mode: str
    runner_enabled: bool
    expected_run_status: str | None


MIGRATION_VARIANTS: dict[str, MigrationBoundaryVariant] = {
    "dispatch_request_not_reached": MigrationBoundaryVariant(
        api_mode="suppress_request",
        deployment_mode="normal",
        runner_enabled=True,
        expected_run_status=None,
    ),
    "workflow_queued_runner_unavailable": MigrationBoundaryVariant(
        api_mode="drop_response",
        deployment_mode="normal",
        runner_enabled=False,
        expected_run_status="waiting",
    ),
    "migration_applied_workflow_failed": MigrationBoundaryVariant(
        api_mode="drop_response",
        deployment_mode="drop_response",
        runner_enabled=True,
        expected_run_status="failure",
    ),
    "workflow_completed_dispatch_response_lost": MigrationBoundaryVariant(
        api_mode="drop_response",
        deployment_mode="normal",
        runner_enabled=True,
        expected_run_status="success",
    ),
}
FORGEJO_MIGRATION_VARIANTS = tuple(MIGRATION_VARIANTS)


class ForgejoMigrationFaultController:
    def __init__(
        self,
        *,
        api_control_url: str = "http://127.0.0.1:9091",
        deployment_control_url: str = "http://127.0.0.1:9096",
        requester: Callable[
            [str, str, str, dict[str, Any] | None], dict[str, Any]
        ] = _json_request,
    ) -> None:
        self.api_control_url = api_control_url
        self.deployment_control_url = deployment_control_url
        self.requester = requester

    def _set(self, url: str, mode: str) -> None:
        result = self.requester(url, "PUT", "/mode", {"mode": mode})
        if result.get("mode") != mode:
            raise RuntimeError(f"gateway did not enter {mode!r}: {result}")

    def restore(self) -> None:
        self._set(self.api_control_url, "normal")
        self._set(self.deployment_control_url, "normal")

    def arm(self, variant: str) -> MigrationBoundaryVariant:
        try:
            specification = MIGRATION_VARIANTS[variant]
        except KeyError as error:
            raise ValueError(
                f"unknown Forgejo migration variant: {variant}"
            ) from error
        self.restore()
        self._set(self.deployment_control_url, specification.deployment_mode)
        self._set(self.api_control_url, specification.api_mode)
        return specification

    def disarm_api(self) -> None:
        self._set(self.api_control_url, "normal")

    def disarm_deployment(self) -> None:
        self._set(self.deployment_control_url, "normal")
