from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from typing import Any

from .forgejo_api import ForgejoAPI


@dataclass(frozen=True)
class ForgejoPublicationPrefix:
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
    release_tag: str
    protected_release_tag: str
    expected_assets: tuple[dict[str, Any], ...]
    protected_asset_name: str
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ForgejoPublicationPrefixBuilder:
    """Create the successful, persistent prefix for the publication family."""

    OWNER = "aftermath"
    REPOSITORY = "artifact-publication"
    BASE_BRANCH = "release/2026.08"
    FEATURE_BRANCH = "release/2026.08-publication"
    PROTECTED_BRANCH = "work/next-release"
    RELEASE_TAG = "v2026.08.0"
    PROTECTED_RELEASE_TAG = "v2026.07.3"
    COORDINATOR_TARGET = (
        "http://webhook-fault-gateway:8080/webhooks/events"
    )
    PROVENANCE_TARGET = (
        "http://provenance-webhook-fault-gateway:8080/webhooks/events"
    )
    BINARY_NAME = "aftermath-agent_2026.08.0_linux_amd64.tar.gz"
    CHECKSUM_NAME = f"{BINARY_NAME}.sha256"
    SBOM_NAME = "aftermath-agent_2026.08.0.spdx.json"
    PROTECTED_ASSET_NAME = "aftermath-agent_2026.07.3.sha256"

    def __init__(self, client: ForgejoAPI):
        self.client = client
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
        """Wait for Forgejo's asynchronous pull-request patch check.

        A newly created pull request is initially reported as non-mergeable
        while Forgejo prepares and tests its merge patch.  Calling the merge
        endpoint during that native transition returns HTTP 405 with
        ``Please try again later``.  Prefix construction must wait for the
        authoritative PR state instead of relying on runner speed.
        """

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

    @classmethod
    def _asset_sources(cls) -> tuple[dict[str, str], ...]:
        binary = (
            "Aftermath Agent v2026.08.0\n"
            "platform=linux-amd64\n"
            "build=approved-release-2026-08\n"
        )
        checksum = hashlib.sha256(binary.encode("utf-8")).hexdigest()
        sbom = json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "name": "aftermath-agent-v2026.08.0",
                "documentNamespace": (
                    "https://aftermath.invalid/spdx/v2026.08.0"
                ),
                "packages": [
                    {
                        "name": "aftermath-agent",
                        "versionInfo": "2026.08.0",
                    }
                ],
            },
            sort_keys=True,
            indent=2,
        ) + "\n"
        return (
            {
                "name": cls.BINARY_NAME,
                "source_path": f"dist/{cls.BINARY_NAME}",
                "content": binary,
            },
            {
                "name": cls.CHECKSUM_NAME,
                "source_path": f"dist/{cls.CHECKSUM_NAME}",
                "content": f"{checksum}  {cls.BINARY_NAME}\n",
            },
            {
                "name": cls.SBOM_NAME,
                "source_path": f"dist/{cls.SBOM_NAME}",
                "content": sbom,
            },
        )

    def build(self) -> ForgejoPublicationPrefix:
        owner = self.OWNER
        repository = self.REPOSITORY
        repo = self._record(
            "create_repository",
            {"name": repository, "private": True, "auto_init": True},
            self.client.create_repository(repository),
        )
        milestone = self._record(
            "create_milestone",
            {"title": "August 2026 production release"},
            self.client.create_milestone(
                owner,
                repository,
                title="August 2026 production release",
                description="Approved release train v2026.08.0",
            ),
        )
        issue = self._record(
            "create_issue",
            {"title": "Publish the approved Linux release bundle"},
            self.client.create_issue(
                owner,
                repository,
                title="Publish the approved Linux release bundle",
                body=(
                    "The binary, checksum and SPDX SBOM must be published "
                    "together."
                ),
                milestone=int(milestone["id"]),
            ),
        )
        self._record(
            "create_branch",
            {"name": self.BASE_BRANCH, "from_ref": "main"},
            self.client.create_branch(
                owner, repository, name=self.BASE_BRANCH
            ),
        )
        self._record(
            "edit_repository",
            {"default_branch": self.BASE_BRANCH},
            self.client.edit_repository(
                owner,
                repository,
                {"default_branch": self.BASE_BRANCH},
            ),
        )
        self._record(
            "create_branch",
            {"name": self.FEATURE_BRANCH, "from_ref": self.BASE_BRANCH},
            self.client.create_branch(
                owner,
                repository,
                name=self.FEATURE_BRANCH,
                from_ref=self.BASE_BRANCH,
            ),
        )
        assets = self._asset_sources()
        for asset in assets:
            self._record(
                "create_file",
                {
                    "path": asset["source_path"],
                    "branch": self.FEATURE_BRANCH,
                },
                self.client.create_file(
                    owner,
                    repository,
                    path=asset["source_path"],
                    content=asset["content"],
                    branch=self.FEATURE_BRANCH,
                    message=f"Add approved artifact {asset['name']}",
                ),
            )
        manifest = {
            "release": self.RELEASE_TAG,
            "target": self.BASE_BRANCH,
            "assets": [
                {
                    "name": asset["name"],
                    "source_path": asset["source_path"],
                    "sha256": hashlib.sha256(
                        asset["content"].encode("utf-8")
                    ).hexdigest(),
                }
                for asset in assets
            ],
            "required_consumers": [
                "release-coordinator",
                "provenance-registry",
            ],
        }
        self._record(
            "create_file",
            {
                "path": "release/publication-manifest.json",
                "branch": self.FEATURE_BRANCH,
            },
            self.client.create_file(
                owner,
                repository,
                path="release/publication-manifest.json",
                content=json.dumps(manifest, indent=2) + "\n",
                branch=self.FEATURE_BRANCH,
                message="Record the approved release publication manifest",
            ),
        )
        pull = self._record(
            "create_pull_request",
            {"head": self.FEATURE_BRANCH, "base": self.BASE_BRANCH},
            self.client.create_pull_request(
                owner,
                repository,
                title="Approve the v2026.08.0 publication bundle",
                body=(
                    "Fixes #1\n\nBinary, checksum and SBOM were approved "
                    "for publication."
                ),
                head=self.FEATURE_BRANCH,
                base=self.BASE_BRANCH,
            ),
        )
        self._record(
            "create_branch",
            {
                "name": self.PROTECTED_BRANCH,
                "from_ref": self.BASE_BRANCH,
            },
            self.client.create_branch(
                owner,
                repository,
                name=self.PROTECTED_BRANCH,
                from_ref=self.BASE_BRANCH,
            ),
        )
        self._record(
            "create_file",
            {
                "path": "docs/next-release.md",
                "branch": self.PROTECTED_BRANCH,
            },
            self.client.create_file(
                owner,
                repository,
                path="docs/next-release.md",
                content="Work for the next release remains open.\n",
                branch=self.PROTECTED_BRANCH,
                message="Start next release notes",
            ),
        )
        protected_pull = self._record(
            "create_pull_request",
            {
                "head": self.PROTECTED_BRANCH,
                "base": self.BASE_BRANCH,
            },
            self.client.create_pull_request(
                owner,
                repository,
                title="Prepare the next release notes",
                body="Do not merge as part of v2026.08.0.",
                head=self.PROTECTED_BRANCH,
                base=self.BASE_BRANCH,
            ),
        )
        protected_issue = self._record(
            "create_issue",
            {"title": "Plan the September release"},
            self.client.create_issue(
                owner,
                repository,
                title="Plan the September release",
                body="This remains open after the August publication.",
            ),
        )
        protected_release = self._record(
            "create_release",
            {
                "tag": self.PROTECTED_RELEASE_TAG,
                "target": "main",
            },
            self.client.create_release(
                owner,
                repository,
                tag=self.PROTECTED_RELEASE_TAG,
                target="main",
                title="July maintenance release",
                body="Previously published and unrelated.",
            ),
        )
        self._record(
            "create_release_attachment",
            {
                "release_id": int(protected_release["id"]),
                "name": self.PROTECTED_ASSET_NAME,
            },
            self.client.create_release_attachment(
                owner,
                repository,
                int(protected_release["id"]),
                name=self.PROTECTED_ASSET_NAME,
                content=b"protected-july-checksum\n",
            ),
        )
        self._record(
            "create_branch_protection",
            {"rule": "release/*"},
            self.client.create_branch_protection(
                owner, repository, rule="release/*"
            ),
        )
        coordinator = self._record(
            "create_hook",
            {
                "target_url": self.COORDINATOR_TARGET,
                "events": ["release"],
            },
            self.client.create_hook(
                owner,
                repository,
                target_url=self.COORDINATOR_TARGET,
                events=["release"],
            ),
        )
        provenance = self._record(
            "create_hook",
            {
                "target_url": self.PROVENANCE_TARGET,
                "events": ["release"],
            },
            self.client.create_hook(
                owner,
                repository,
                target_url=self.PROVENANCE_TARGET,
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
        expected = {
            "owner": repo["owner"]["login"],
            "linked_issue_index": int(issue["number"]),
            "pull_request_index": int(pull["number"]),
            "protected_pull_request_index": int(
                protected_pull["number"]
            ),
            "protected_issue_index": int(protected_issue["number"]),
        }
        if expected != {
            "owner": owner,
            "linked_issue_index": 1,
            "pull_request_index": 2,
            "protected_pull_request_index": 3,
            "protected_issue_index": 4,
        }:
            raise RuntimeError(
                f"Forgejo publication fixture indexes drifted: {expected}"
            )
        return ForgejoPublicationPrefix(
            owner=owner,
            repository=repository,
            milestone_id=int(milestone["id"]),
            linked_issue_index=1,
            pull_request_index=2,
            protected_pull_request_index=3,
            protected_issue_index=4,
            coordinator_hook_id=int(coordinator["id"]),
            provenance_hook_id=int(provenance["id"]),
            base_branch=self.BASE_BRANCH,
            feature_branch=self.FEATURE_BRANCH,
            release_tag=self.RELEASE_TAG,
            protected_release_tag=self.PROTECTED_RELEASE_TAG,
            expected_assets=tuple(
                {
                    "name": item["name"],
                    "source_path": item["source_path"],
                    "sha256": hashlib.sha256(
                        item["content"].encode("utf-8")
                    ).hexdigest(),
                }
                for item in assets
            ),
            protected_asset_name=self.PROTECTED_ASSET_NAME,
            trace=tuple(self.trace),
        )
