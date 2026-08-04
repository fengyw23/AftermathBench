from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .forgejo_faults import _json_request


@dataclass(frozen=True)
class PromotionBoundaryVariant:
    api_mode: str
    runner_enabled: bool
    expected_run_status: str | None
    workflow_inputs: dict[str, str]
    finalize_release_metadata: bool = False


PROMOTION_VARIANTS: dict[str, PromotionBoundaryVariant] = {
    "dispatch_request_not_reached": PromotionBoundaryVariant(
        "suppress_request", True, None, {}
    ),
    "workflow_queued_runner_unavailable": PromotionBoundaryVariant(
        "drop_response", False, "waiting", {}
    ),
    "signed_bundle_completed_deployment_missing": PromotionBoundaryVariant(
        "drop_response", True, "failure", {"stop_after": "bundle"}
    ),
    "deployment_completed_attestation_missing": PromotionBoundaryVariant(
        "drop_response", True, "failure", {"stop_after": "deployment"}
    ),
    "attestation_accepted_release_metadata_missing": PromotionBoundaryVariant(
        "drop_response", True, "success", {}
    ),
    "promotion_completed_response_lost": PromotionBoundaryVariant(
        "drop_response", True, "success", {}, True
    ),
}
FORGEJO_PROMOTION_VARIANTS = tuple(PROMOTION_VARIANTS)


class ForgejoPromotionFaultController:
    def __init__(
        self,
        *,
        api_control_url: str = "http://127.0.0.1:9091",
        deployment_control_url: str = "http://127.0.0.1:9096",
        webhook_control_url: str = "http://127.0.0.1:9093",
        requester: Callable[
            [str, str, str, dict[str, Any] | None], dict[str, Any]
        ] = _json_request,
    ) -> None:
        self.api_control_url = api_control_url
        self.deployment_control_url = deployment_control_url
        self.webhook_control_url = webhook_control_url
        self.requester = requester

    def _set(self, url: str, mode: str) -> None:
        result = self.requester(url, "PUT", "/mode", {"mode": mode})
        if result.get("mode") != mode:
            raise RuntimeError(f"gateway did not enter {mode!r}: {result}")

    def restore(self) -> None:
        for url in (
            self.api_control_url,
            self.deployment_control_url,
            self.webhook_control_url,
        ):
            self._set(url, "normal")

    def arm(self, variant: str) -> PromotionBoundaryVariant:
        try:
            specification = PROMOTION_VARIANTS[variant]
        except KeyError as error:
            raise ValueError(f"unknown Forgejo promotion variant: {variant}") from error
        self.restore()
        self._set(self.api_control_url, specification.api_mode)
        return specification

    def disarm_api(self) -> None:
        self._set(self.api_control_url, "normal")


__all__ = [
    "FORGEJO_PROMOTION_VARIANTS",
    "PROMOTION_VARIANTS",
    "ForgejoPromotionFaultController",
    "PromotionBoundaryVariant",
]
