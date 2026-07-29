from __future__ import annotations

import json
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

    def create_issue(
        self,
        owner: str,
        repository: str,
        *,
        title: str,
        body: str,
    ) -> dict[str, Any]:
        result = self.post(
            f"/repos/{owner}/{repository}/issues",
            {"title": title, "body": body},
        )
        if not isinstance(result, dict):
            raise TypeError("Forgejo returned no issue document")
        return result

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
