from __future__ import annotations

import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from typing import Any


@dataclass(frozen=True)
class WebhookDelivery:
    uuid: str
    status: str


class _WebhookHistoryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.last_status: str | None = None
        self.capture_uuid = False
        self.uuid_parts: list[str] = []
        self.deliveries: list[WebhookDelivery] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag != "span":
            return
        attributes = dict(attrs)
        classes = set(str(attributes.get("class", "")).split())
        if "text" in classes:
            if "green" in classes:
                self.last_status = "succeeded"
            elif "orange" in classes:
                self.last_status = "pending"
            elif "red" in classes:
                self.last_status = "failed"
        if "shortsha" in classes:
            self.capture_uuid = True
            self.uuid_parts = []

    def handle_data(self, data: str) -> None:
        if self.capture_uuid:
            self.uuid_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "span" or not self.capture_uuid:
            return
        uuid = "".join(self.uuid_parts).strip()
        if uuid and self.last_status:
            self.deliveries.append(
                WebhookDelivery(uuid=uuid, status=self.last_status)
            )
        self.capture_uuid = False
        self.uuid_parts = []
        self.last_status = None


def parse_webhook_history(html: str) -> tuple[WebhookDelivery, ...]:
    parser = _WebhookHistoryParser()
    parser.feed(html)
    return tuple(parser.deliveries)


class ForgejoWebSession:
    """Uses Forgejo's native settings UI for hook history and replay."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        opener: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.opener = opener or urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
        self.signed_in = False

    def _open(
        self,
        request: urllib.request.Request,
    ) -> Any:
        return self.opener.open(request, timeout=15)

    def login(self) -> None:
        payload = urllib.parse.urlencode(
            {
                "user_name": self.username,
                "password": self.password,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/user/login",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/user/login",
            },
        )
        with self._open(request) as response:
            response.read()
            final_url = response.geturl()
            status = response.status
        if status != 200 or "/user/login" in final_url:
            raise RuntimeError(
                f"Forgejo web sign-in failed: HTTP {status} {final_url}"
            )
        self.signed_in = True

    def _ensure_login(self) -> None:
        if not self.signed_in:
            self.login()

    def webhook_history(
        self,
        owner: str,
        repository: str,
        hook_id: int,
    ) -> tuple[WebhookDelivery, ...]:
        self._ensure_login()
        url = (
            f"{self.base_url}/{urllib.parse.quote(owner)}/"
            f"{urllib.parse.quote(repository)}/settings/hooks/{hook_id}"
        )
        with self._open(urllib.request.Request(url, method="GET")) as response:
            html = response.read().decode("utf-8")
        return parse_webhook_history(html)

    def replay_webhook(
        self,
        owner: str,
        repository: str,
        hook_id: int,
        delivery_uuid: str,
    ) -> dict[str, Any]:
        history = self.webhook_history(owner, repository, hook_id)
        known = {delivery.uuid for delivery in history}
        if delivery_uuid not in known:
            raise ValueError(
                f"delivery UUID is not present in native history: "
                f"{delivery_uuid}"
            )
        base = (
            f"{self.base_url}/{urllib.parse.quote(owner)}/"
            f"{urllib.parse.quote(repository)}/settings/hooks/{hook_id}"
        )
        request = urllib.request.Request(
            f"{base}/replay/{urllib.parse.quote(delivery_uuid)}",
            data=b"",
            method="POST",
            headers={
                "Origin": self.base_url,
                "Referer": base,
                # Forgejo uses Go's CrossOriginProtection middleware for
                # authenticated web POSTs.  A browser sends this Fetch
                # Metadata header; urllib does not.  Supplying the truthful
                # same-origin value makes this session reproduce the native
                # UI request instead of being rejected before the replay
                # handler runs.
                "Sec-Fetch-Site": "same-origin",
            },
        )
        with self._open(request) as response:
            response.read()
            return {
                "status": response.status,
                "url": response.geturl(),
                "replay_request_accepted": True,
                "source_delivery_uuid": delivery_uuid,
                "new_delivery_state": "not_checked",
            }
