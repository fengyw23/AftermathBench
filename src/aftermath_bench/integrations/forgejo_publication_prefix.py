from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from .forgejo_api import ForgejoAPI
from .forgejo_publication_instance import (
    DEFAULT_FORGEJO_PUBLICATION_INSTANCE,
    ForgejoPublicationInstanceSpec,
)


@dataclass(frozen=True)
class ForgejoPublicationPrefix:
    scenario_id: str
    instance_spec_sha256: str
    owner: str
    repository: str
    milestone_id: int
    linked_issue_index: int
    pull_request_index: int
    protected_pull_request_index: int
    protected_issue_index: int
    coordinator_hook_id: int
    provenance_hook_id: int
    base_branch: str
    feature_branch: str
    protected_branch: str
    release_tag: str
    protected_release_tag: str
    manifest_path: str
    branch_protection_rule: str
    release_title: str
    release_body: str
    required_consumers: tuple[str, str]
    expected_assets: tuple[dict[str, Any], ...]
    protected_asset_name: str
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ForgejoPublicationPrefixBuilder:
    """Create the successful, persistent prefix for one publication instance."""

    def __init__(
        self,
        client: ForgejoAPI,
        instance: ForgejoPublicationInstanceSpec | None = None,
    ):
        self.client = client
        self.instance = (
            instance
            if instance is not None
            else DEFAULT_FORGEJO_PUBLICATION_INSTANCE
        )
        self.instance.validate()
        self.trace: list[dict[str, Any]] = []

    def _record(
        self,
        tool: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> Any:
        self.trace.append(
            {
                "tool": tool,
                "arguments": arguments,
                "result": result,
            }
        )
        return result

    def _wait_for_pull_mergeable(
        self,
        owner: str,
        repository: str,
        index: int,
        *,
        attempts: int = 30,
        interval_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """Wait for Forgejo's asynchronous pull-request patch check."""

        last: dict[str, Any] = {}
        for attempt in range(attempts):
            last = self.client.get_pull_request(owner, repository, index)
            if bool(last.get("mergeable")):
                return last
            if attempt + 1 < attempts:
                time.sleep(interval_seconds)
        raise RuntimeError(
            "Forgejo pull request did not become mergeable within "
            f"{attempts} authoritative reads: {last}"
        )

    def _asset_sources(self) -> tuple[dict[str, str], ...]:
        spec = self.instance
        binary = (
            f"{spec.package_name} v{spec.version}\n"
            f"platform={spec.platform.replace('_', '-')}\n"
            f"build={spec.build_id}\n"
        )
        checksum = hashlib.sha256(binary.encode("utf-8")).hexdigest()
        sbom = json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "name": f"{spec.package_slug}-v{spec.version}",
                "documentNamespace": (
                    f"https://{spec.owner}.invalid/spdx/v{spec.version}"
                ),
                "packages": [
                    {
                        "name": spec.package_slug,
                        "versionInfo": spec.version,
                    }
                ],
            },
            sort_keys=True,
            indent=2,
        ) + "\n"
        return (
            {
                "role": "binary",
                "name": spec.binary_name,
                "source_path": f"dist/{spec.binary_name}",
                "content": binary,
            },
            {
                "role": "checksum",
                "name": spec.checksum_name,
                "source_path": f"dist/{spec.checksum_name}",
                "content": f"{checksum}  {spec.binary_name}\n",
            },
            {
                "role": "sbom",
                "name": spec.sbom_name,
                "source_path": f"dist/{spec.sbom_name}",
                "content": sbom,
            },
        )

    def build(self) -> ForgejoPublicationPrefix:
        spec = self.instance
        owner = spec.owner
        repository = spec.repository
        repo = self._record(
            "create_repository",
            {"name": repository, "private": True, "auto_init": True},
            self.client.create_repository(repository),
        )
        milestone = self._record(
            "create_milestone",
            {"title": spec.milestone_title},
            self.client.create_milestone(
                owner,
                repository,
                title=spec.milestone_title,
                description=f"Approved release train {spec.release_tag}",
            ),
        )
        issue = self._record(
            "create_issue",
            {"title": spec.target_issue_title},
            self.client.create_issue(
                owner,
                repository,
                title=spec.target_issue_title,
                body=(
                    "The binary, checksum and SPDX SBOM must be published "
                    "together."
                ),
                milestone=int(milestone["id"]),
            ),
        )
        self._record(
            "create_branch",
            {"name": spec.base_branch, "from_ref": "main"},
            self.client.create_branch(
                owner, repository, name=spec.base_branch
            ),
        )
        self._record(
            "edit_repository",
            {"default_branch": spec.base_branch},
            self.client.edit_repository(
                owner,
                repository,
                {"default_branch": spec.base_branch},
            ),
        )
        self._record(
            "create_branch",
            {"name": spec.feature_branch, "from_ref": spec.base_branch},
            self.client.create_branch(
                owner,
                repository,
                name=spec.feature_branch,
                from_ref=spec.base_branch,
            ),
        )
        assets = self._asset_sources()
        for asset in assets:
            self._record(
                "create_file",
                {
                    "path": asset["source_path"],
                    "branch": spec.feature_branch,
                },
                self.client.create_file(
                    owner,
                    repository,
                    path=asset["source_path"],
                    content=asset["content"],
                    branch=spec.feature_branch,
                    message=f"Add approved artifact {asset['name']}",
                ),
            )
        manifest = {
            "release": spec.release_tag,
            "target": spec.base_branch,
            "assets": [
                {
                    "role": asset["role"],
                    "name": asset["name"],
                    "source_path": asset["source_path"],
                    "sha256": hashlib.sha256(
                        asset["content"].encode("utf-8")
                    ).hexdigest(),
                }
                for asset in assets
            ],
            "required_consumers": list(spec.required_consumers),
        }
        self._record(
            "create_file",
            {
                "path": spec.manifest_path,
                "branch": spec.feature_branch,
            },
            self.client.create_file(
                owner,
                repository,
                path=spec.manifest_path,
                content=json.dumps(manifest, indent=2) + "\n",
                branch=spec.feature_branch,
                message="Record the approved release publication manifest",
            ),
        )
        pull = self._record(
            "create_pull_request",
            {"head": spec.feature_branch, "base": spec.base_branch},
            self.client.create_pull_request(
                owner,
                repository,
                title=f"Approve the {spec.release_tag} publication bundle",
                body=(
                    f"Fixes #{int(issue['number'])}\n\nBinary, checksum and "
                    "SBOM were approved for publication."
                ),
                head=spec.feature_branch,
                base=spec.base_branch,
            ),
        )
        self._record(
            "create_branch",
            {
                "name": spec.protected_branch,
                "from_ref": spec.base_branch,
            },
            self.client.create_branch(
                owner,
                repository,
                name=spec.protected_branch,
                from_ref=spec.base_branch,
            ),
        )
        self._record(
            "create_file",
            {
                "path": spec.protected_file_path,
                "branch": spec.protected_branch,
            },
            self.client.create_file(
                owner,
                repository,
                path=spec.protected_file_path,
                content="Work for the next release remains open.\n",
                branch=spec.protected_branch,
                message="Start next release notes",
            ),
        )
        protected_pull = self._record(
            "create_pull_request",
            {
                "head": spec.protected_branch,
                "base": spec.base_branch,
            },
            self.client.create_pull_request(
                owner,
                repository,
                title=spec.protected_pull_title,
                body=f"Do not merge as part of {spec.release_tag}.",
                head=spec.protected_branch,
                base=spec.base_branch,
            ),
        )
        protected_issue = self._record(
            "create_issue",
            {"title": spec.protected_issue_title},
            self.client.create_issue(
                owner,
                repository,
                title=spec.protected_issue_title,
                body="This remains open after the target publication.",
            ),
        )
        protected_release = self._record(
            "create_release",
            {
                "tag": spec.protected_release_tag,
                "target": "main",
            },
            self.client.create_release(
                owner,
                repository,
                tag=spec.protected_release_tag,
                target="main",
                title=spec.protected_release_title,
                body="Previously published and unrelated.",
            ),
        )
        self._record(
            "create_release_attachment",
            {
                "release_id": int(protected_release["id"]),
                "name": spec.protected_asset_name,
            },
            self.client.create_release_attachment(
                owner,
                repository,
                int(protected_release["id"]),
                name=spec.protected_asset_name,
                content=b"protected-prior-release-checksum\n",
            ),
        )
        self._record(
            "create_branch_protection",
            {"rule": spec.branch_protection_rule},
            self.client.create_branch_protection(
                owner,
                repository,
                rule=spec.branch_protection_rule,
            ),
        )
        coordinator = self._record(
            "create_hook",
            {
                "target_url": spec.coordinator_target,
                "events": ["release"],
            },
            self.client.create_hook(
                owner,
                repository,
                target_url=spec.coordinator_target,
                events=["release"],
            ),
        )
        provenance = self._record(
            "create_hook",
            {
                "target_url": spec.provenance_target,
                "events": ["release"],
            },
            self.client.create_hook(
                owner,
                repository,
                target_url=spec.provenance_target,
                events=["release"],
            ),
        )
        self._wait_for_pull_mergeable(
            owner,
            repository,
            int(pull["number"]),
        )
        self._record(
            "merge_pull_request",
            {"index": int(pull["number"])},
            self.client.merge_pull_request(
                owner,
                repository,
                int(pull["number"]),
            ),
        )
        observed = {
            "owner": str(repo["owner"]["login"]),
            "linked_issue_index": int(issue["number"]),
            "pull_request_index": int(pull["number"]),
            "protected_pull_request_index": int(
                protected_pull["number"]
            ),
            "protected_issue_index": int(protected_issue["number"]),
        }
        if observed["owner"] != owner:
            raise RuntimeError(
                f"Forgejo publication fixture owner drifted: {observed}"
            )
        return ForgejoPublicationPrefix(
            scenario_id=spec.scenario_id,
            instance_spec_sha256=spec.sha256,
            owner=owner,
            repository=repository,
            milestone_id=int(milestone["id"]),
            linked_issue_index=observed["linked_issue_index"],
            pull_request_index=observed["pull_request_index"],
            protected_pull_request_index=observed[
                "protected_pull_request_index"
            ],
            protected_issue_index=observed["protected_issue_index"],
            coordinator_hook_id=int(coordinator["id"]),
            provenance_hook_id=int(provenance["id"]),
            base_branch=spec.base_branch,
            feature_branch=spec.feature_branch,
            protected_branch=spec.protected_branch,
            release_tag=spec.release_tag,
            protected_release_tag=spec.protected_release_tag,
            manifest_path=spec.manifest_path,
            branch_protection_rule=spec.branch_protection_rule,
            release_title=spec.release_title,
            release_body=spec.release_body,
            required_consumers=spec.required_consumers,
            expected_assets=tuple(
                {
                    "role": item["role"],
                    "name": item["name"],
                    "source_path": item["source_path"],
                    "sha256": hashlib.sha256(
                        item["content"].encode("utf-8")
                    ).hexdigest(),
                }
                for item in assets
            ),
            protected_asset_name=spec.protected_asset_name,
            trace=tuple(self.trace),
        )
