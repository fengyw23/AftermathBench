from __future__ import annotations

from dataclasses import dataclass

from .forgejo_publication_faults import ForgejoPublicationFaultController


@dataclass(frozen=True)
class PackageProvenanceBoundaryVariant:
    preloaded_file_roles: tuple[str, ...]
    attempted_operation: str
    api_mode: str
    release_committed: bool
    downstream_mode: str


PACKAGE_PROVENANCE_VARIANTS = {
    "package_request_not_reached": PackageProvenanceBoundaryVariant(
        preloaded_file_roles=(),
        attempted_operation="upload_binary",
        api_mode="suppress_request",
        release_committed=False,
        downstream_mode="normal",
    ),
    "package_binary_committed_response_lost": (
        PackageProvenanceBoundaryVariant(
            preloaded_file_roles=(),
            attempted_operation="upload_binary",
            api_mode="drop_response",
            release_committed=False,
            downstream_mode="normal",
        )
    ),
    "package_complete_index_missing": PackageProvenanceBoundaryVariant(
        preloaded_file_roles=("binary", "checksum", "sbom", "signature"),
        attempted_operation="create_index_release",
        api_mode="suppress_request",
        release_committed=False,
        downstream_mode="normal",
    ),
    "package_complete_index_accepted_response_lost": (
        PackageProvenanceBoundaryVariant(
            preloaded_file_roles=(
                "binary",
                "checksum",
                "sbom",
                "signature",
            ),
            attempted_operation="create_index_release",
            api_mode="drop_response",
            release_committed=True,
            downstream_mode="drop_response",
        )
    ),
}

FORGEJO_PACKAGE_PROVENANCE_VARIANTS = tuple(PACKAGE_PROVENANCE_VARIANTS)


class ForgejoPackageProvenanceFaultController(
    ForgejoPublicationFaultController
):
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
            specification.downstream_mode,
        )
        self.api._set_mode(
            self.provenance_gateway_control_url,
            specification.downstream_mode,
        )
        return specification


__all__ = [
    "FORGEJO_PACKAGE_PROVENANCE_VARIANTS",
    "PACKAGE_PROVENANCE_VARIANTS",
    "ForgejoPackageProvenanceFaultController",
    "PackageProvenanceBoundaryVariant",
]
