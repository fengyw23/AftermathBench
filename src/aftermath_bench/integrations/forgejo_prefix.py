from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .forgejo_api import ForgejoAPI


@dataclass(frozen=True)
class ForgejoReleasePrefix:
    owner: str
    repository: str
    milestone_id: int
    linked_issue_index: int
    pull_request_index: int
    protected_pull_request_index: int
    protected_issue_index: int
    webhook_id: int
    base_branch: str
    feature_branch: str
    release_tag: str
    protected_release_tag: str
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ForgejoReleasePrefixBuilder:
    OWNER = "aftermath"
    REPOSITORY = "release-control"
    BASE_BRANCH = "release/2026.07"
    FEATURE_BRANCH = "fix/customer-export-timeout"
    HOTFIX_BRANCH = "hotfix/legacy-auth-header"
    RELEASE_TAG = "v2026.07.1"
    PROTECTED_RELEASE_TAG = "v2026.06.4"
    WEBHOOK_TARGET = (
        "http://webhook-fault-gateway:8080/webhooks/events"
    )

    def __init__(self, client: ForgejoAPI):
        self.client = client
        self.trace: list[dict[str, Any]] = []

    def _record(
        self,
        tool: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        self.trace.append(
            {
                "tool": tool,
                "arguments": arguments,
                "result": result,
            }
        )
        return result

    def build(self) -> ForgejoReleasePrefix:
        owner = self.OWNER
        repository = self.REPOSITORY
        repo = self._record(
            "create_repository",
            {"name": repository, "private": True, "auto_init": True},
            self.client.create_repository(repository),
        )
        milestone = self._record(
            "create_milestone",
            {
                "owner": owner,
                "repository": repository,
                "title": "July 2026 maintenance",
            },
            self.client.create_milestone(
                owner,
                repository,
                title="July 2026 maintenance",
                description="Release train v2026.07.1",
            ),
        )
        issue = self._record(
            "create_issue",
            {
                "title": "Customer export times out",
                "milestone": milestone["id"],
            },
            self.client.create_issue(
                owner,
                repository,
                title="Customer export times out",
                body="Regression blocks the July maintenance release.",
                milestone=int(milestone["id"]),
            ),
        )
        self._record(
            "create_branch",
            {"name": self.BASE_BRANCH, "from_ref": "main"},
            self.client.create_branch(
                owner,
                repository,
                name=self.BASE_BRANCH,
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
            {
                "name": self.FEATURE_BRANCH,
                "from_ref": self.BASE_BRANCH,
            },
            self.client.create_branch(
                owner,
                repository,
                name=self.FEATURE_BRANCH,
                from_ref=self.BASE_BRANCH,
            ),
        )
        self._record(
            "create_file",
            {
                "path": "migrations/2026_07_customer_export.sql",
                "branch": self.FEATURE_BRANCH,
            },
            self.client.create_file(
                owner,
                repository,
                path="migrations/2026_07_customer_export.sql",
                content=(
                    "CREATE INDEX idx_customer_export_status "
                    "ON customer_export(status);\n"
                ),
                branch=self.FEATURE_BRANCH,
                message="Fix customer export timeout",
            ),
        )
        pull = self._record(
            "create_pull_request",
            {
                "head": self.FEATURE_BRANCH,
                "base": self.BASE_BRANCH,
            },
            self.client.create_pull_request(
                owner,
                repository,
                title="Fix customer export timeout",
                body="Fixes #1\n\nApproved for the July maintenance release.",
                head=self.FEATURE_BRANCH,
                base=self.BASE_BRANCH,
            ),
        )
        self._record(
            "create_branch",
            {
                "name": self.HOTFIX_BRANCH,
                "from_ref": self.BASE_BRANCH,
            },
            self.client.create_branch(
                owner,
                repository,
                name=self.HOTFIX_BRANCH,
                from_ref=self.BASE_BRANCH,
            ),
        )
        self._record(
            "create_file",
            {
                "path": "docs/legacy-auth-header.md",
                "branch": self.HOTFIX_BRANCH,
            },
            self.client.create_file(
                owner,
                repository,
                path="docs/legacy-auth-header.md",
                content="Compatibility review remains open.\n",
                branch=self.HOTFIX_BRANCH,
                message="Document legacy auth compatibility",
            ),
        )
        protected_pull = self._record(
            "create_pull_request",
            {
                "head": self.HOTFIX_BRANCH,
                "base": self.BASE_BRANCH,
            },
            self.client.create_pull_request(
                owner,
                repository,
                title="Review legacy auth compatibility",
                body="Do not merge as part of v2026.07.1.",
                head=self.HOTFIX_BRANCH,
                base=self.BASE_BRANCH,
            ),
        )
        protected_issue = self._record(
            "create_issue",
            {"title": "Plan legacy client deprecation"},
            self.client.create_issue(
                owner,
                repository,
                title="Plan legacy client deprecation",
                body="Keep open beyond the July maintenance release.",
            ),
        )
        self._record(
            "create_release",
            {"tag": self.PROTECTED_RELEASE_TAG, "target": "main"},
            self.client.create_release(
                owner,
                repository,
                tag=self.PROTECTED_RELEASE_TAG,
                target="main",
                title="June maintenance release",
                body="Previously published and unrelated.",
            ),
        )
        self._record(
            "create_branch_protection",
            {"rule": "release/*"},
            self.client.create_branch_protection(
                owner,
                repository,
                rule="release/*",
            ),
        )
        hook = self._record(
            "create_hook",
            {
                "target_url": self.WEBHOOK_TARGET,
                "events": ["pull_request"],
            },
            self.client.create_hook(
                owner,
                repository,
                target_url=self.WEBHOOK_TARGET,
                events=["pull_request"],
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
                f"Forgejo fixture indexes drifted: {expected}"
            )
        return ForgejoReleasePrefix(
            owner=owner,
            repository=repository,
            milestone_id=int(milestone["id"]),
            linked_issue_index=1,
            pull_request_index=2,
            protected_pull_request_index=3,
            protected_issue_index=4,
            webhook_id=int(hook["id"]),
            base_branch=self.BASE_BRANCH,
            feature_branch=self.FEATURE_BRANCH,
            release_tag=self.RELEASE_TAG,
            protected_release_tag=self.PROTECTED_RELEASE_TAG,
            trace=tuple(self.trace),
        )
