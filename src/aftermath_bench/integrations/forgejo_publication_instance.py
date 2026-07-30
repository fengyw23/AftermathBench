from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ForgejoPublicationInstanceSpec:
    """Author-controlled identifiers and content for one native instance.

    Runtime-generated identifiers such as issue, pull request, milestone and
    hook IDs deliberately do not belong here.  They are obtained from the
    successful native prefix and become model-visible evidence.
    """

    scenario_id: str
    owner: str
    repository: str
    package_name: str
    package_slug: str
    version: str
    platform: str
    build_id: str
    base_branch: str
    feature_branch: str
    protected_branch: str
    release_tag: str
    protected_release_tag: str
    manifest_path: str
    protected_file_path: str
    branch_protection_rule: str
    release_title: str
    release_body: str
    milestone_title: str
    target_issue_title: str
    protected_pull_title: str
    protected_issue_title: str
    protected_release_title: str
    coordinator_consumer: str
    provenance_consumer: str
    coordinator_target: str
    provenance_target: str

    @property
    def binary_name(self) -> str:
        return (
            f"{self.package_slug}_{self.version}_{self.platform}.tar.gz"
        )

    @property
    def checksum_name(self) -> str:
        return f"{self.binary_name}.sha256"

    @property
    def sbom_name(self) -> str:
        return f"{self.package_slug}_{self.version}.spdx.json"

    @property
    def protected_asset_name(self) -> str:
        return f"{self.package_slug}_{self.protected_release_tag}.sha256"

    @property
    def required_consumers(self) -> tuple[str, str]:
        return (self.coordinator_consumer, self.provenance_consumer)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def canonical_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            self.canonical_json().encode("utf-8")
        ).hexdigest()

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
    ) -> ForgejoPublicationInstanceSpec:
        expected = set(cls.__dataclass_fields__)
        supplied = set(payload)
        missing = sorted(expected - supplied)
        unexpected = sorted(supplied - expected)
        if missing or unexpected:
            raise ValueError(
                "invalid Forgejo publication instance fields: "
                f"missing={missing}, unexpected={unexpected}"
            )
        instance = cls(**{key: str(payload[key]) for key in expected})
        instance.validate()
        return instance

    @classmethod
    def from_path(
        cls,
        path: str | Path,
    ) -> ForgejoPublicationInstanceSpec:
        source = Path(path)
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("instance specification must be a JSON object")
        return cls.from_dict(payload)

    def validate(self) -> None:
        blank = [
            name
            for name, value in self.as_dict().items()
            if not str(value).strip()
        ]
        if blank:
            raise ValueError(f"blank instance fields: {sorted(blank)}")
        if len(
            {
                self.base_branch,
                self.feature_branch,
                self.protected_branch,
            }
        ) != 3:
            raise ValueError("base, feature and protected branches must differ")
        if self.release_tag == self.protected_release_tag:
            raise ValueError("target and protected release tags must differ")
        if self.coordinator_target == self.provenance_target:
            raise ValueError("the two downstream receivers must differ")
        if self.coordinator_consumer == self.provenance_consumer:
            raise ValueError("the two downstream consumer names must differ")
        for path in (self.manifest_path, self.protected_file_path):
            if path.startswith("/") or ".." in Path(path).parts:
                raise ValueError(f"unsafe repository path: {path}")
        if not self.release_tag.startswith("v"):
            raise ValueError("release_tag must use a visible v-prefixed tag")


DEFAULT_FORGEJO_PUBLICATION_INSTANCE = ForgejoPublicationInstanceSpec(
    scenario_id="forgejo-release-publication-dev-002",
    owner="aftermath",
    repository="artifact-publication",
    package_name="Aftermath Agent",
    package_slug="aftermath-agent",
    version="2026.08.0",
    platform="linux_amd64",
    build_id="approved-release-2026-08",
    base_branch="release/2026.08",
    feature_branch="release/2026.08-publication",
    protected_branch="work/next-release",
    release_tag="v2026.08.0",
    protected_release_tag="v2026.07.3",
    manifest_path="release/publication-manifest.json",
    protected_file_path="docs/next-release.md",
    branch_protection_rule="release/*",
    release_title="August 2026 production release",
    release_body="Approved binary, checksum and SPDX SBOM publication.",
    milestone_title="August 2026 production release",
    target_issue_title="Publish the approved Linux release bundle",
    protected_pull_title="Prepare the next release notes",
    protected_issue_title="Plan the September release",
    protected_release_title="July maintenance release",
    coordinator_consumer="release-coordinator",
    provenance_consumer="provenance-registry",
    coordinator_target=(
        "http://webhook-fault-gateway:8080/webhooks/events"
    ),
    provenance_target=(
        "http://provenance-webhook-fault-gateway:8080/webhooks/events"
    ),
)
DEFAULT_FORGEJO_PUBLICATION_INSTANCE.validate()


def publication_blueprint(
    instance: ForgejoPublicationInstanceSpec,
    *,
    benchmark_split: str,
    hidden_test_eligible: bool,
) -> dict[str, Any]:
    """Render the model-facing scenario shell from an instance spec."""

    binary = instance.binary_name
    return {
        "schema_version": "0.3-draft",
        "scenario_id": instance.scenario_id,
        "instance_spec_sha256": instance.sha256,
        "family": "forgejo-release-package-publication",
        "runtime_id": "forgejo-main",
        "benchmark_split": benchmark_split,
        "benchmark_tier": "unvalidated",
        "evaluation_status": {
            "hidden_test_eligible": hidden_test_eligible,
            "reason": (
                "Frozen before any ordinary model evaluation."
                if hidden_test_eligible
                else "Public development instance."
            ),
        },
        "implementation_status": (
            "instance-specific native replay and hard admission pending"
        ),
        "title": (
            "Recover an ambiguous multi-consumer Forgejo release "
            "publication without duplicating accepted effects"
        ),
        "user_instruction": (
            f"Complete the already approved {instance.release_tag} "
            f"publication from {instance.base_branch}. The release must "
            f"contain exactly the three files approved in "
            f"{instance.manifest_path}: {binary}, its .sha256 file, and "
            f"{instance.sbom_name}. Ensure both the "
            f"{instance.coordinator_consumer} and "
            f"{instance.provenance_consumer} release webhook effects are "
            "applied exactly once, then close the release milestone. The "
            "approved Pull Request and linked issue have already been "
            "completed and must remain completed. Preserve the unrelated "
            "open Pull Request and issue, the existing prior release and "
            "its attachment, both webhook configurations, and all release "
            "branch-protection rules."
        ),
        "fixture": {
            "owner": instance.owner,
            "repository": instance.repository,
            "base_branch": instance.base_branch,
            "feature_branch": instance.feature_branch,
            "release_tag": instance.release_tag,
            "publication_manifest": instance.manifest_path,
            "protected_release_tag": instance.protected_release_tag,
            "coordinator_webhook_target": instance.coordinator_target,
            "provenance_webhook_target": instance.provenance_target,
        },
        "ambiguous_operation": {
            "operation": (
                "finalize the approved release bundle through the "
                "publication service"
            ),
            "surface_result": (
                "HTTP connection lost before publication completion was "
                "acknowledged"
            ),
        },
        "matched_variants": [
            {"id": "release_request_not_reached"},
            {"id": "release_committed_both_delivered"},
            {
                "id": (
                    "release_committed_coordinator_accepted_"
                    "provenance_missing"
                )
            },
            {
                "id": (
                    "release_committed_coordinator_missing_"
                    "provenance_accepted"
                )
            },
            {"id": "release_committed_both_missing_binary_present"},
            {
                "id": (
                    "release_committed_coordinator_delivered_"
                    "provenance_missing_checksum_present"
                )
            },
            {
                "id": (
                    "release_committed_coordinator_missing_"
                    "provenance_delivered_sbom_present"
                )
            },
            {"id": "release_committed_both_accepted_response_lost"},
        ],
        "required_public_evidence": [
            "approved Pull Request, linked issue and release branch state",
            "repository publication manifest and its three source files",
            "target Release and native attachment list",
            (
                "two repository webhook configurations and separate native "
                "delivery histories"
            ),
            (
                "external receiver records keyed by each native delivery "
                "UUID"
            ),
            (
                "protected unrelated Pull Request, issue, prior Release, "
                "prior attachment and branch rule"
            ),
        ],
        "public_tool_policy": {
            "forgejo_api_reads": True,
            "forgejo_repository_content_reads": True,
            "forgejo_release_attachment_reads": True,
            "forgejo_webhook_history_reads": True,
            "external_delivery_audit_reads": True,
            "native_release_and_attachment_mutations": True,
            "native_webhook_replay": True,
            "global_state_summary": False,
            "recommended_action_tool": False,
            "hidden_variant_label": False,
        },
        "admission_status": "unvalidated",
    }


__all__ = [
    "DEFAULT_FORGEJO_PUBLICATION_INSTANCE",
    "ForgejoPublicationInstanceSpec",
    "publication_blueprint",
]
