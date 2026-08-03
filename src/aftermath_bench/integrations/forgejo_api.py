from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ForgejoAPI:
    base_url: str
    token: str
    timeout: int = 30

    @property
    def server_url(self) -> str:
        """Return the Forgejo origin used by non-v1 package routes."""

        parsed = urllib.parse.urlsplit(self.base_url.rstrip("/"))
        path = parsed.path.rstrip("/")
        path = path.removesuffix("/api/v1")
        return urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, path, "", "")
        ).rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = (
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            if payload is not None
            else None
        )
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"token {self.token}",
                **(
                    {"Content-Type": "application/json"}
                    if payload is not None
                    else {}
                ),
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Forgejo API {method} {path} returned HTTP "
                f"{error.code}: {detail[:1000]}"
            ) from error

    def _request_bytes(
        self,
        method: str,
        path: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> Any:
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"token {self.token}",
                "Content-Type": content_type,
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Forgejo API {method} {path} returned HTTP "
                f"{error.code}: {detail[:1000]}"
            ) from error

    def _request_package_bytes(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
    ) -> bytes:
        """Call Forgejo's native ``/api/packages`` registry surface."""

        request = urllib.request.Request(
            f"{self.server_url}/{path.lstrip('/')}",
            data=body,
            headers={
                "Accept": "application/octet-stream",
                "Authorization": f"token {self.token}",
                **(
                    {"Content-Type": "application/octet-stream"}
                    if body is not None
                    else {}
                ),
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Forgejo package API {method} {path} returned HTTP "
                f"{error.code}: {detail[:1000]}"
            ) from error

    def download(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/octet-stream",
                "Authorization": f"token {self.token}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Forgejo attachment GET {url} returned HTTP "
                f"{error.code}: {detail[:1000]}"
            ) from error

    def get(
        self,
        path: str,
        *,
        query: dict[str, str] | None = None,
    ) -> Any:
        if query:
            path = f"{path}?{urllib.parse.urlencode(query)}"
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> Any:
        return self._request("PATCH", path, payload)

    def delete(self, path: str) -> Any:
        return self._request("DELETE", path)

    def create_repository(
        self,
        name: str,
        *,
        private: bool = True,
        auto_init: bool = True,
    ) -> dict[str, Any]:
        result = self.post(
            "/user/repos",
            {
                "name": name,
                "private": private,
                "auto_init": auto_init,
                "default_branch": "main",
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no repository document")
        return result

    def edit_repository(
        self,
        owner: str,
        repository: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.patch(
            f"/repos/{owner}/{repository}",
            payload,
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no repository document")
        return result

    def create_issue(
        self,
        owner: str,
        repository: str,
        *,
        title: str,
        body: str,
        milestone: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "body": body}
        if milestone is not None:
            payload["milestone"] = milestone
        result = self.post(
            f"/repos/{owner}/{repository}/issues",
            payload,
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no issue document")
        return result

    def create_branch(
        self,
        owner: str,
        repository: str,
        *,
        name: str,
        from_ref: str = "main",
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/branches",
            {
                "new_branch_name": name,
                "old_ref_name": from_ref,
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no branch document")
        return result

    def create_file(
        self,
        owner: str,
        repository: str,
        *,
        path: str,
        content: str,
        branch: str,
        message: str,
    ) -> dict[str, Any]:
        encoded_path = urllib.parse.quote(path, safe="/")
        result = self.post(
            f"/repos/{owner}/{repository}/contents/{encoded_path}",
            {
                "content": base64.b64encode(
                    content.encode("utf-8")
                ).decode("ascii"),
                "branch": branch,
                "message": message,
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no file commit document")
        return result

    def create_pull_request(
        self,
        owner: str,
        repository: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/pulls",
            {
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no Pull Request document")
        return result

    def get_pull_request(
        self,
        owner: str,
        repository: str,
        index: int,
    ) -> dict[str, Any]:
        result = self.get(
            f"/repos/{owner}/{repository}/pulls/{index}"
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no Pull Request document")
        return result

    def merge_pull_request(
        self,
        owner: str,
        repository: str,
        index: int,
        *,
        method: str = "merge",
        delete_branch: bool = False,
    ) -> Any:
        return self.post(
            f"/repos/{owner}/{repository}/pulls/{index}/merge",
            {
                "Do": method,
                "delete_branch_after_merge": delete_branch,
            },
        )

    def create_hook(
        self,
        owner: str,
        repository: str,
        *,
        target_url: str,
        events: list[str],
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/hooks",
            {
                "type": "forgejo",
                "config": {
                    "url": target_url,
                    "content_type": "json",
                },
                "events": events,
                "active": True,
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no webhook document")
        return result

    def create_branch_protection(
        self,
        owner: str,
        repository: str,
        *,
        rule: str,
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/branch_protections",
            {
                "rule_name": rule,
                "enable_push": False,
                "required_approvals": 0,
                "block_on_rejected_reviews": True,
                "dismiss_stale_approvals": True,
                "apply_to_admins": False,
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no branch-protection document")
        return result

    def list_branch_protections(
        self,
        owner: str,
        repository: str,
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/branch_protections"
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no branch-protection list")
        return [item for item in result if isinstance(item, dict)]

    def list_hooks(
        self,
        owner: str,
        repository: str,
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/hooks",
            query={"limit": "50"},
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no webhook list")
        return [item for item in result if isinstance(item, dict)]

    def create_release(
        self,
        owner: str,
        repository: str,
        *,
        tag: str,
        target: str,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/releases",
            {
                "tag_name": tag,
                "target_commitish": target,
                "name": title,
                "body": body,
                "draft": False,
                "prerelease": False,
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no release document")
        return result

    def list_releases(
        self,
        owner: str,
        repository: str,
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/releases",
            query={"limit": "50"},
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no release list")
        return [item for item in result if isinstance(item, dict)]

    def get_repository_content(
        self,
        owner: str,
        repository: str,
        *,
        path: str,
        ref: str,
    ) -> dict[str, Any]:
        encoded_path = urllib.parse.quote(path, safe="/")
        result = self.get(
            f"/repos/{owner}/{repository}/contents/{encoded_path}",
            query={"ref": ref},
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no repository content")
        return result

    def get_release_by_tag(
        self,
        owner: str,
        repository: str,
        tag: str,
    ) -> dict[str, Any]:
        encoded_tag = urllib.parse.quote(tag, safe="")
        result = self.get(
            f"/repos/{owner}/{repository}/releases/tags/{encoded_tag}"
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no release document")
        return result

    def list_release_attachments(
        self,
        owner: str,
        repository: str,
        release_id: int,
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/releases/{release_id}/assets"
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no release attachment list")
        return [item for item in result if isinstance(item, dict)]

    def create_release_attachment(
        self,
        owner: str,
        repository: str,
        release_id: int,
        *,
        name: str,
        content: bytes,
    ) -> dict[str, Any]:
        encoded_name = urllib.parse.quote(name, safe="")
        content_type = (
            mimetypes.guess_type(name)[0] or "application/octet-stream"
        )
        result = self._request_bytes(
            "POST",
            (
                f"/repos/{owner}/{repository}/releases/{release_id}/assets"
                f"?name={encoded_name}"
            ),
            content,
            content_type=content_type,
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no release attachment")
        return result

    def list_packages(
        self,
        owner: str,
        *,
        package_type: str = "generic",
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        params = {"type": package_type, "limit": "50"}
        if query:
            params["q"] = query
        result = self.get(f"/packages/{owner}", query=params)
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no package list")
        return [item for item in result if isinstance(item, dict)]

    def get_package(
        self,
        owner: str,
        *,
        package_type: str,
        name: str,
        version: str,
    ) -> dict[str, Any]:
        components = [
            urllib.parse.quote(value, safe="")
            for value in (owner, package_type, name, version)
        ]
        result = self.get("/packages/" + "/".join(components))
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no package document")
        return result

    def list_package_files(
        self,
        owner: str,
        *,
        package_type: str,
        name: str,
        version: str,
    ) -> list[dict[str, Any]]:
        components = [
            urllib.parse.quote(value, safe="")
            for value in (owner, package_type, name, version)
        ]
        result = self.get(
            "/packages/" + "/".join(components) + "/files"
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no package file list")
        return [item for item in result if isinstance(item, dict)]

    def link_package(
        self,
        owner: str,
        *,
        package_type: str,
        name: str,
        repository: str,
    ) -> Any:
        components = [
            urllib.parse.quote(value, safe="")
            for value in (owner, package_type, name)
        ]
        encoded_repository = urllib.parse.quote(repository, safe="")
        return self.post(
            "/packages/"
            + "/".join(components)
            + f"/-/link/{encoded_repository}",
            {},
        )

    def upload_generic_package_file(
        self,
        owner: str,
        *,
        name: str,
        version: str,
        filename: str,
        content: bytes,
    ) -> None:
        components = [
            urllib.parse.quote(value, safe="")
            for value in (owner, name, version, filename)
        ]
        self._request_package_bytes(
            "PUT",
            "/api/packages/"
            + components[0]
            + "/generic/"
            + "/".join(components[1:]),
            content,
        )

    def download_generic_package_file(
        self,
        owner: str,
        *,
        name: str,
        version: str,
        filename: str,
    ) -> bytes:
        components = [
            urllib.parse.quote(value, safe="")
            for value in (owner, name, version, filename)
        ]
        return self._request_package_bytes(
            "GET",
            "/api/packages/"
            + components[0]
            + "/generic/"
            + "/".join(components[1:]),
        )

    def list_issues(
        self,
        owner: str,
        repository: str,
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/issues",
            query={"state": "all", "limit": "50"},
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no issue list")
        return [item for item in result if isinstance(item, dict)]

    def edit_issue(
        self,
        owner: str,
        repository: str,
        index: int,
        *,
        state: str,
    ) -> dict[str, Any]:
        result = self.patch(
            f"/repos/{owner}/{repository}/issues/{int(index)}",
            {"state": state},
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no issue document")
        return result

    def create_issue_comment(
        self,
        owner: str,
        repository: str,
        index: int,
        *,
        body: str,
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/issues/{int(index)}/comments",
            {"body": body},
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no issue comment")
        return result

    def list_issue_comments(
        self,
        owner: str,
        repository: str,
        index: int,
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/issues/{int(index)}/comments",
            query={"limit": "50"},
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no issue-comment list")
        return [item for item in result if isinstance(item, dict)]

    def create_milestone(
        self,
        owner: str,
        repository: str,
        *,
        title: str,
        description: str,
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/milestones",
            {
                "title": title,
                "description": description,
                "state": "open",
            },
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no milestone document")
        return result

    def get_milestone(
        self,
        owner: str,
        repository: str,
        milestone_id: int,
    ) -> dict[str, Any]:
        result = self.get(
            f"/repos/{owner}/{repository}/milestones/{milestone_id}"
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no milestone document")
        return result

    def edit_milestone(
        self,
        owner: str,
        repository: str,
        milestone_id: int,
        *,
        state: str,
    ) -> dict[str, Any]:
        result = self.patch(
            f"/repos/{owner}/{repository}/milestones/{milestone_id}",
            {"state": state},
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no milestone document")
        return result

    def dispatch_workflow(
        self,
        owner: str,
        repository: str,
        *,
        workflow: str,
        ref: str,
        inputs: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a native Forgejo Actions workflow and return its run ID."""

        encoded_workflow = urllib.parse.quote(workflow, safe="")
        result = self.post(
            f"/repos/{owner}/{repository}/actions/workflows/"
            f"{encoded_workflow}/dispatches",
            {
                "ref": ref,
                "inputs": inputs or {},
                "return_run_info": True,
            },
        )
        if not isinstance(result, dict) or not result.get("id"):
            raise TypeError("Forgejo returned no dispatched workflow run")
        return result

    def list_action_runs(
        self,
        owner: str,
        repository: str,
        *,
        workflow: str | None = None,
        ref: str | None = None,
    ) -> list[dict[str, Any]]:
        query = {"limit": "50"}
        if workflow is not None:
            query["workflow_id"] = workflow
        if ref is not None:
            query["ref"] = ref
        result = self.get(
            f"/repos/{owner}/{repository}/actions/runs",
            query=query,
        )
        runs = result.get("workflow_runs") if isinstance(result, dict) else None
        if not isinstance(runs, list):
            raise TypeError("Forgejo returned no workflow-run list")
        return [run for run in runs if isinstance(run, dict)]

    def get_action_run(
        self, owner: str, repository: str, run_id: int
    ) -> dict[str, Any]:
        result = self.get(
            f"/repos/{owner}/{repository}/actions/runs/{int(run_id)}"
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no workflow run")
        return result

    def list_action_run_jobs(
        self, owner: str, repository: str, run_id: int
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/actions/runs/{int(run_id)}/jobs"
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no workflow-job list")
        return [job for job in result if isinstance(job, dict)]

    def list_action_run_artifacts(
        self, owner: str, repository: str, run_id: int
    ) -> list[dict[str, Any]]:
        result = self.get(
            f"/repos/{owner}/{repository}/actions/runs/{int(run_id)}/artifacts",
            query={"limit": "50"},
        )
        if not isinstance(result, list):
            raise TypeError("Forgejo returned no workflow-artifact list")
        return [artifact for artifact in result if isinstance(artifact, dict)]

    def cancel_action_run(
        self, owner: str, repository: str, run_id: int
    ) -> Any:
        return self.post(
            f"/repos/{owner}/{repository}/actions/runs/{int(run_id)}/cancel",
            {},
        )
