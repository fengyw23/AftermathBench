from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EnterpriseOpsConfig:
    base_url: str
    database_id: str
    context_headers: dict[str, str]
    mcp_endpoint: str = "/mcp"


class EnterpriseOpsHTTPAdapter:
    """Transparent adapter around EnterpriseOps-Gym's public HTTP contract.

    The upstream public repository exposes database seeding, SQL verification,
    and MCP client code, but the domain tool implementations run in separately
    distributed Docker images. This adapter intentionally uses only those
    documented public boundaries.
    """

    def __init__(self, config: EnterpriseOpsConfig):
        self.config = config
        self._request_id = 0

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-database-id": self.config.database_id,
            **self.config.context_headers,
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_tools(self) -> tuple[str, ...]:
        self._request_id += 1
        response = self._post(
            self.config.mcp_endpoint,
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/list",
                "params": {},
            },
        )
        return tuple(tool["name"] for tool in response["result"]["tools"])

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        self._request_id += 1
        response = self._post(
            self.config.mcp_endpoint,
            {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": kwargs},
            },
        )
        if "error" in response:
            return {"ok": False, "error": response["error"]}
        return {"ok": True, "data": response.get("result")}

    def query(self, sql: str) -> dict[str, Any]:
        return self._post(
            "/api/query",
            {
                "query": sql,
                "database_id": self.config.database_id,
            },
        )

    def snapshot_queries(self, queries: dict[str, str]) -> dict[str, Any]:
        return {name: self.query(sql) for name, sql in sorted(queries.items())}

    def snapshot(self) -> dict[str, Any]:
        raise RuntimeError(
            "EnterpriseOps-Gym has no public whole-database export endpoint. "
            "Use snapshot_queries() with an explicit task-relevant query set."
        )

