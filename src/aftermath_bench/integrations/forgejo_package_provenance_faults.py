from __future__ import annotations

from dataclasses import dataclass

from .forgejo_publication_faults import ForgejoPublicationFaultController


@dataclass(frozen=True)
class PackageProvenanceBoundaryVariant:
    preloaded_file_roles: tuple[str, ...]
    preclosed_tracking_positions: tuple[int, ...]
    postcommit_tracking_positions: tuple[int, ...]
    attempted_operation: str
    api_mode: str
    release_committed: bool
    coordinator_mode: str
    provenance_mode: str


PACKAGE_PROVENANCE_VARIANTS = {
    "package_request_not_reached": PackageProvenanceBoundaryVariant(
        preloaded_file_roles=(),
        preclosed_tracking_positions=(),
        postcommit_tracking_positions=(),
        attempted_operation="upload_binary",
        api_mode="suppress_request",
        release_committed=False,
        coordinator_mode="normal",
        provenance_mode="normal",
    ),
    "package_binary_committed_response_lost": (
        PackageProvenanceBoundaryVariant(
            preloaded_file_roles=(),
            preclosed_tracking_positions=(),
            postcommit_tracking_positions=(),
            attempted_operation="upload_binary",
            api_mode="drop_response",
            release_committed=False,
            coordinator_mode="normal",
            provenance_mode="normal",
        )
    ),
    "package_complete_index_missing": PackageProvenanceBoundaryVariant(
        preloaded_file_roles=("binary", "checksum", "sbom", "signature"),
        preclosed_tracking_positions=(0,),
        postcommit_tracking_positions=(),
        attempted_operation="create_index_release",
        api_mode="suppress_request",
        release_committed=False,
        coordinator_mode="normal",
        provenance_mode="normal",
    ),
    "package_complete_index_accepted_response_lost": (
        PackageProvenanceBoundaryVariant(
            preloaded_file_roles=(
                "binary",
                "checksum",
                "sbom",
                "signature",
            ),
            preclosed_tracking_positions=(0,),
            postcommit_tracking_positions=(1,),
            attempted_operation="create_index_release",
            api_mode="drop_response",
            release_committed=True,
            coordinator_mode="drop_response",
            provenance_mode="suppress_request",
        )
    ),
}

FORGEJO_PACKAGE_PROVENANCE_VARIANTS = tuple(PACKAGE_PROVENANCE_VARIANTS)


class ForgejoPackageProvenanceFaultController(ForgejoPublicationFaultController):
    def arm(self, variant: str) -> PackageProvenanceBoundaryVariant:
        try:
            specification = PACKAGE_PROVENANCE_VARIANTS[variant]
        except KeyError as error:
            raise ValueError(
                f"unknown Forgejo package-provenance variant: {variant}"
            ) from error
        self.restore()
        self.api._set_mode(
            self.api.api_gateway_control_url,
            specification.api_mode,
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


__all__ = [
    "FORGEJO_PACKAGE_PROVENANCE_VARIANTS",
    "PACKAGE_PROVENANCE_VARIANTS",
    "ForgejoPackageProvenanceFaultController",
    "PackageProvenanceBoundaryVariant",
]
