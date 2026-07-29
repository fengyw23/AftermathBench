from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


FORGEJO_FAULT_VARIANTS = (
    "merge_request_not_reached",
    "merge_committed_delivery_succeeded",
    "merge_committed_receiver_accepted_response_lost",
    "merge_committed_delivery_request_not_reached",
)


def _json_request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Forgejo fault control failed ({error.code}): {detail}"
        ) from error
    return json.loads(body) if body else {}


class ForgejoFaultController:
    def __init__(
        self,
        *,
        api_gateway_control_url: str = "http://127.0.0.1:9091",
        webhook_gateway_control_url: str = "http://127.0.0.1:9093",
        requester: Callable[
            [str, str, str, dict[str, Any] | None],
            dict[str, Any],
        ] = _json_request,
    ) -> None:
        self.api_gateway_control_url = api_gateway_control_url
        self.webhook_gateway_control_url = webhook_gateway_control_url
        self.requester = requester

    def _set_mode(self, control_url: str, mode: str) -> None:
        response = self.requester(
            control_url,
            "PUT",
            "/mode",
            {"mode": mode},
        )
        if response.get("mode") != mode:
            raise RuntimeError(
                f"gateway did not enter mode {mode!r}: {response}"
            )

    def restore(self) -> None:
        self._set_mode(self.api_gateway_control_url, "normal")
        self._set_mode(self.webhook_gateway_control_url, "normal")

    def arm(self, variant: str) -> None:
        if variant not in FORGEJO_FAULT_VARIANTS:
            raise ValueError(f"unknown Forgejo fault variant: {variant}")
        self.restore()
        if variant == "merge_request_not_reached":
            self._set_mode(
                self.api_gateway_control_url,
                "suppress_request",
            )
            return
        self._set_mode(self.api_gateway_control_url, "drop_response")
        if variant == "merge_committed_receiver_accepted_response_lost":
            self._set_mode(
                self.webhook_gateway_control_url,
                "drop_response",
            )
        elif variant == "merge_committed_delivery_request_not_reached":
            self._set_mode(
                self.webhook_gateway_control_url,
                "suppress_request",
            )

    def disarm_api_after_surface_failure(self) -> None:
        self._set_mode(self.api_gateway_control_url, "normal")

    def disarm_webhook_after_attempt(self) -> None:
        self._set_mode(self.webhook_gateway_control_url, "normal")
