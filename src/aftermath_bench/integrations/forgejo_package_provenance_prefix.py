from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from .forgejo_api import ForgejoAPI
from .forgejo_publication_instance import ForgejoPublicationInstanceSpec
from .forgejo_publication_prefix import ForgejoPublicationPrefixBuilder


class _PackagePublicationPrefixBuilder(ForgejoPublicationPrefixBuilder):
    """Add the approved signature before the base branch becomes protected."""

    def _asset_sources(self) -> tuple[dict[str, str], ...]:
        assets = super()._asset_sources()
        binary = next(item for item in assets if item["role"] == "binary")
        signature_name = (
            f"{self.instance.package_slug}_{self.instance.version}.sigstore.json"
        )
        signature = (
            json.dumps(
                {
                    "mediaType": (
                        "application/vnd.dev.sigstore.bundle+json;version=0.3"
                    ),
                    "subject": {
                        "name": binary["name"],
                        "sha256": hashlib.sha256(
                            binary["content"].encode("utf-8")
                        ).hexdigest(),
                    },
                    "verificationMaterial": {
                        "certificateIdentity": "release-bot@aftermath.invalid",
                        "issuer": "https://forgejo.invalid/actions",
                    },
                },
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        return assets + (
            {
                "role": "signature",
                "name": signature_name,
                "source_path": f"dist/{signature_name}",
                "content": signature,
            },
        )


@dataclass(frozen=True)
class ForgejoPackageProvenancePrefix:
    scenario_id: str
    instance_spec_sha256: str
    owner: str
    repository: str
    base_branch: str
    pull_request_index: int
    linked_issue_index: int
    milestone_id: int
    protected_pull_request_index: int
    protected_issue_index: int
    tracking_issue_indexes: tuple[int, ...]
    protected_release_tag: str
    protected_asset_name: str
    branch_protection_rule: str
    package_name: str
    package_version: str
    protected_package_version: str
    package_index_release_tag: str
    package_index_release_title: str
    package_index_release_body: str
    coordinator_hook_id: int
    provenance_hook_id: int
    expected_package_files: tuple[dict[str, Any], ...]
    protected_package_files: tuple[dict[str, Any], ...]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ForgejoPackageProvenancePrefixBuilder:
    """Build a package-registry task on the admitted Forgejo release fixture."""

    def __init__(
        self,
        client: ForgejoAPI,
        instance: ForgejoPublicationInstanceSpec,
    ) -> None:
        self.client = client
        self.instance = instance

    @staticmethod
    def _sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _repository_source(
        self,
        *,
        owner: str,
        repository: str,
        path: str,
        ref: str,
    ) -> bytes:
        import base64

        document = self.client.get_repository_content(
            owner,
            repository,
            path=path,
            ref=ref,
        )
        return base64.b64decode(
            str(document["content"]).replace("\n", ""),
            validate=True,
        )

    def build(self) -> ForgejoPackageProvenancePrefix:
        spec = self.instance
        base = _PackagePublicationPrefixBuilder(self.client, spec).build()
        trace = list(base.trace)

        tracking_issue_indexes: list[int] = []
        for title, body in (
            (
                "Verify the 3.7.0 package signature and SBOM",
                "Close only after the target package files match approved sources.",
            ),
            (
                "Reconcile the 3.7.0 package index release",
                "Close only after exactly one index Release exists.",
            ),
            (
                "Audit 3.7.0 downstream package notifications",
                "Close only after both receiver effects are present exactly once.",
            ),
        ):
            issue = self.client.create_issue(
                base.owner,
                base.repository,
                title=title,
                body=body,
                milestone=base.milestone_id,
            )
            tracking_issue_indexes.append(int(issue["number"]))
            trace.append(
                {
                    "tool": "create_issue",
                    "arguments": {"title": title},
                    "result": issue,
                    "kind": "write",
                    "status": "success",
                }
            )

        expected = []
        for source in base.expected_assets:
            content = self._repository_source(
                owner=base.owner,
                repository=base.repository,
                path=str(source["source_path"]),
                ref=base.base_branch,
            )
            expected.append(
                {
                    "role": source["role"],
                    "name": str(source["name"]),
                    "source_path": str(source["source_path"]),
                    "sha256": self._sha256(content),
                }
            )

        protected_version = spec.protected_release_tag.removeprefix("v")
        protected_contents = {
            f"{spec.package_slug}_{protected_version}.tar.gz": (
                f"protected package {spec.package_slug} {protected_version}\n"
            ).encode(),
            f"{spec.package_slug}_{protected_version}.sigstore.json": (
                b'{"protected":true,"signature":"retained"}\n'
            ),
            f"{spec.package_slug}_{protected_version}.spdx.json": (
                b'{"spdxVersion":"SPDX-2.3","protected":true}\n'
            ),
        }
        protected_files = []
        for filename, content in protected_contents.items():
            self.client.upload_generic_package_file(
                base.owner,
                name=spec.package_slug,
                version=protected_version,
                filename=filename,
                content=content,
            )
            protected_files.append(
                {"name": filename, "sha256": self._sha256(content)}
            )
            trace.append(
                {
                    "tool": "upload_generic_package_file",
                    "arguments": {
                        "name": spec.package_slug,
                        "version": protected_version,
                        "filename": filename,
                    },
                    "result": {"created": True},
                    "kind": "write",
                    "status": "success",
                }
            )
        self.client.link_package(
            base.owner,
            package_type="generic",
            name=spec.package_slug,
            repository=base.repository,
        )
        trace.append(
            {
                "tool": "link_package",
                "arguments": {
                    "name": spec.package_slug,
                    "repository": base.repository,
                },
                "result": {"linked": True},
                "kind": "write",
                "status": "success",
            }
        )

        return ForgejoPackageProvenancePrefix(
            scenario_id=spec.scenario_id,
            instance_spec_sha256=spec.sha256,
            owner=base.owner,
            repository=base.repository,
            base_branch=base.base_branch,
            pull_request_index=base.pull_request_index,
            linked_issue_index=base.linked_issue_index,
            milestone_id=base.milestone_id,
            protected_pull_request_index=base.protected_pull_request_index,
            protected_issue_index=base.protected_issue_index,
            tracking_issue_indexes=tuple(tracking_issue_indexes),
            protected_release_tag=base.protected_release_tag,
            protected_asset_name=base.protected_asset_name,
            branch_protection_rule=base.branch_protection_rule,
            package_name=spec.package_slug,
            package_version=spec.version,
            protected_package_version=protected_version,
            package_index_release_tag=base.release_tag,
            package_index_release_title=(
                f"Package index {spec.package_slug} {spec.version}"
            ),
            package_index_release_body=(
                "Generic package files, signature and SPDX SBOM verified."
            ),
            coordinator_hook_id=base.coordinator_hook_id,
            provenance_hook_id=base.provenance_hook_id,
            expected_package_files=tuple(expected),
            protected_package_files=tuple(protected_files),
            trace=tuple(trace),
        )


__all__ = [
    "ForgejoPackageProvenancePrefix",
    "ForgejoPackageProvenancePrefixBuilder",
]
