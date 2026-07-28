from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FrappeConfig:
    base_url: str
    api_key: str
    api_secret: str
    timeout_seconds: int = 30


class FrappeHTTPAdapter:
    """Thin client for Frappe's public REST boundary.

    Business transitions remain inside the pinned Frappe/ERPNext runtime. The
    adapter deliberately does not reproduce document validation, accounting,
    inventory, workflow, or transaction logic in benchmark code.
    """

    def __init__(self, config: FrappeConfig):
        self.config = config

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.config.base_url.rstrip('/')}{path}",
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": (
                    f"token {self.config.api_key}:{self.config.api_secret}"
                ),
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout_seconds,
            ) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Frappe request failed ({error.code}): {detail}"
            ) from error
        if not body:
            return {}
        decoded = json.loads(body.decode("utf-8"))
        return decoded if isinstance(decoded, dict) else {"data": decoded}

    @staticmethod
    def _resource_path(doctype: str, name: str | None = None) -> str:
        encoded_doctype = urllib.parse.quote(doctype, safe="")
        path = f"/api/resource/{encoded_doctype}"
        if name is not None:
            path += f"/{urllib.parse.quote(name, safe='')}"
        return path

    def create_resource(
        self,
        doctype: str,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request("POST", self._resource_path(doctype), document)

    def get_resource(self, doctype: str, name: str) -> dict[str, Any]:
        return self._request("GET", self._resource_path(doctype, name))

    def update_resource(
        self,
        doctype: str,
        name: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request("PUT", self._resource_path(doctype, name), fields)

    def delete_resource(self, doctype: str, name: str) -> dict[str, Any]:
        return self._request("DELETE", self._resource_path(doctype, name))

    def call_method(
        self,
        dotted_method: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        method = urllib.parse.quote(dotted_method, safe=".")
        return self._request(
            "POST",
            f"/api/method/{method}",
            arguments or {},
        )

    def submit_document(
        self,
        doctype: str,
        name: str,
    ) -> dict[str, Any]:
        return self.call_method(
            "frappe.client.submit",
            {"doc": {"doctype": doctype, "name": name}},
        )

    def cancel_document(
        self,
        doctype: str,
        name: str,
    ) -> dict[str, Any]:
        return self.call_method(
            "frappe.client.cancel",
            {"doctype": doctype, "name": name},
        )

