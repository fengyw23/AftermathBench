from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DeploymentTargetAPI:
    base_url: str
    timeout: int = 30

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/{path.lstrip('/')}",
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"deployment target {method} {path} returned HTTP {error.code}: {detail[:1000]}"
            ) from error

    def state(self) -> dict[str, Any]:
        result = self._request("GET", "/state")
        if not isinstance(result, dict):
            raise TypeError("deployment target returned no state document")
        return result

    def apply_migration(self, **payload: str) -> dict[str, Any]:
        return self._request("POST", "/migrations", payload)

    def register_artifact(self, **payload: str) -> dict[str, Any]:
        return self._request("POST", "/artifacts", payload)

    def request_deployment(self, **payload: str) -> dict[str, Any]:
        return self._request("POST", "/deployments", payload)

    def run_workers(self) -> dict[str, Any]:
        return self._request("POST", "/workers/run", {})

    def record_audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/audit-events", payload)
