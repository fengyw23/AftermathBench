from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


ACCEPT_MANIFESTS = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)


@dataclass(frozen=True)
class RegistryReference:
    registry: str
    repository: str
    tag: str

    @property
    def manifest_url(self) -> str:
        return f"https://{self.registry}/v2/{self.repository}/manifests/{self.tag}"


def parse_reference(reference: str) -> RegistryReference:
    if "@" in reference:
        raise ValueError("expected a tag, not an already pinned digest")
    name, separator, tag = reference.rpartition(":")
    if not separator or "/" in tag:
        name, tag = reference, "latest"
    first = name.split("/", 1)[0]
    if "." in first or ":" in first or first == "localhost":
        registry, repository = name.split("/", 1)
    else:
        registry = "registry-1.docker.io"
        repository = name
        if "/" not in repository:
            repository = f"library/{repository}"
    if registry == "docker.io":
        registry = "registry-1.docker.io"
    return RegistryReference(registry, repository, tag)


def _bearer_parameters(header: str) -> dict[str, str]:
    if not header.lower().startswith("bearer "):
        raise RuntimeError(f"unsupported registry authentication: {header}")
    return {
        key: value
        for key, value in re.findall(r'(\w+)="([^"]+)"', header[7:])
    }


def resolve_manifest_digest(reference: str) -> str:
    parsed = parse_reference(reference)
    request = urllib.request.Request(
        parsed.manifest_url,
        headers={"Accept": ACCEPT_MANIFESTS},
        method="HEAD",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            digest = response.headers.get("Docker-Content-Digest")
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise
        parameters = _bearer_parameters(
            error.headers.get("WWW-Authenticate", "")
        )
        query = urllib.parse.urlencode(
            {
                key: parameters[key]
                for key in ("service", "scope")
                if key in parameters
            }
        )
        with urllib.request.urlopen(
            f"{parameters['realm']}?{query}",
            timeout=30,
        ) as response:
            token_payload = json.loads(response.read().decode("utf-8"))
        token = token_payload.get("token") or token_payload["access_token"]
        request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=30) as response:
            digest = response.headers.get("Docker-Content-Digest")
    if not digest or not digest.startswith("sha256:"):
        raise RuntimeError(f"registry did not return a digest for {reference}")
    return digest

