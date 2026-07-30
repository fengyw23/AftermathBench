from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .forgejo_faults import ForgejoFaultController, _json_request


@dataclass(frozen=True)
class PublicationBoundaryVariant:
    release_committed: bool
    coordinator_mode: str
    provenance_mode: str
    preloaded_asset_roles: tuple[str, ...] = ()


PUBLICATION_VARIANTS: dict[str, PublicationBoundaryVariant] = {
    "release_request_not_reached": PublicationBoundaryVariant(
        release_committed=False,
        coordinator_mode="normal",
        provenance_mode="normal",
    ),
    "release_committed_both_delivered": PublicationBoundaryVariant(
        release_committed=True,
        coordinator_mode="normal",
        provenance_mode="normal",
    ),
    "release_committed_coordinator_accepted_provenance_missing": (
        PublicationBoundaryVariant(
            release_committed=True,
            coordinator_mode="drop_response",
            provenance_mode="suppress_request",
        )
    ),
    "release_committed_coordinator_missing_provenance_accepted": (
        PublicationBoundaryVariant(
            release_committed=True,
            coordinator_mode="suppress_request",
            provenance_mode="drop_response",
        )
    ),
    "release_committed_both_missing_binary_present": (
        PublicationBoundaryVariant(
            release_committed=True,
            coordinator_mode="suppress_request",
            provenance_mode="suppress_request",
            preloaded_asset_roles=("binary",),
        )
    ),
    "release_committed_coordinator_delivered_provenance_missing_checksum_present": (
        PublicationBoundaryVariant(
            release_committed=True,
            coordinator_mode="normal",
            provenance_mode="suppress_request",
            preloaded_asset_roles=("checksum",),
        )
    ),
    "release_committed_coordinator_missing_provenance_delivered_sbom_present": (
        PublicationBoundaryVariant(
            release_committed=True,
            coordinator_mode="suppress_request",
            provenance_mode="normal",
            preloaded_asset_roles=("sbom",),
        )
    ),
    "release_committed_both_accepted_response_lost": (
        PublicationBoundaryVariant(
            release_committed=True,
            coordinator_mode="drop_response",
            provenance_mode="drop_response",
        )
    ),
}

FORGEJO_PUBLICATION_VARIANTS = tuple(PUBLICATION_VARIANTS)


class ForgejoPublicationFaultController:
    def __init__(
        self,
        *,
        api_gateway_control_url: str = "http://127.0.0.1:9091",
        coordinator_gateway_control_url: str = "http://127.0.0.1:9093",
        provenance_gateway_control_url: str = "http://127.0.0.1:9094",
        requester: Callable[
            [str, str, str, dict[str, Any] | None],
            dict[str, Any],
        ] = _json_request,
    ) -> None:
        self.api = ForgejoFaultController(
            api_gateway_control_url=api_gateway_control_url,
            webhook_gateway_control_url=coordinator_gateway_control_url,
            requester=requester,
        )
        self.coordinator_gateway_control_url = (
            coordinator_gateway_control_url
        )
        self.provenance_gateway_control_url = provenance_gateway_control_url

    def restore(self) -> None:
        self.api._set_mode(self.api.api_gateway_control_url, "normal")
        self.api._set_mode(self.coordinator_gateway_control_url, "normal")
        self.api._set_mode(self.provenance_gateway_control_url, "normal")

    def arm(self, variant: str) -> PublicationBoundaryVariant:
        try:
            specification = PUBLICATION_VARIANTS[variant]
        except KeyError as error:
            raise ValueError(
                f"unknown Forgejo publication variant: {variant}"
            ) from error
        self.restore()
        self.api._set_mode(
            self.api.api_gateway_control_url,
            (
                "drop_response"
                if specification.release_committed
                else "suppress_request"
            ),
        )
        self.api._set_mode(
            self.coordinator_gateway_control_url,
            specification.coordinator_mode,
        )
        self.api._set_mode(
            self.provenance_gateway_control_url,
            specification.provenance_mode,
        )
        return specification

    def disarm_api_after_surface_failure(self) -> None:
        self.api._set_mode(self.api.api_gateway_control_url, "normal")

    def disarm_webhooks_after_attempt(self) -> None:
        self.api._set_mode(self.coordinator_gateway_control_url, "normal")
        self.api._set_mode(self.provenance_gateway_control_url, "normal")
