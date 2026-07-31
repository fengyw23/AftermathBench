from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tarfile
import tempfile
from collections.abc import Callable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from .integrations.forgejo_api import ForgejoAPI
from .integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
)
from .integrations.forgejo_publication_recovery import (
    ForgejoPublicationEnvironment,
)
from .integrations.forgejo_web import ForgejoWebSession
from .strict_json import loads_strict

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}$"
)
_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "capture_mode",
        "forgejo_sha256",
        "webhook_sink_sha256",
    }
)
_BUNDLE_SCHEMA_VERSION = "1.0"
_BUNDLE_CAPTURE_MODE = "simultaneous_service_quiescence"


class ForgejoPublicationStateEvidenceError(ValueError):
    """Raised when native state evidence cannot be safely established."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ForgejoPublicationStateEvidenceError(
            "native state contains a non-JSON value"
        ) from error
    return rendered.encode("utf-8")


def canonical_state_fingerprint(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def deterministic_state_projection(value: Any) -> Any:
    """Retain every JSON value and every native array position."""

    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ForgejoPublicationStateEvidenceError(
                "native state object keys must be strings"
            )
        return {
            key: deterministic_state_projection(value[key]) for key in sorted(value)
        }
    if isinstance(value, (list, tuple)):
        return [deterministic_state_projection(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ForgejoPublicationStateEvidenceError(
                "native state contains a non-finite number"
            )
        return value
    raise ForgejoPublicationStateEvidenceError(
        f"native state contains unsupported type {type(value).__name__}"
    )


def _reject_symlink_path(path: Path, *, label: str) -> None:
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise ForgejoPublicationStateEvidenceError(
                f"{label} must not traverse a symbolic link"
            )


def _input_file(path: str | Path, *, label: str) -> Path:
    source = Path(path)
    if ".." in source.parts:
        raise ForgejoPublicationStateEvidenceError(
            f"{label} must not contain parent traversal"
        )
    _reject_symlink_path(source, label=label)
    try:
        resolved = source.resolve(strict=True)
    except OSError as error:
        raise ForgejoPublicationStateEvidenceError(f"{label} does not exist") from error
    if not resolved.is_file():
        raise ForgejoPublicationStateEvidenceError(f"{label} must be a regular file")
    return resolved


def _input_bytes(path: str | Path, *, label: str) -> tuple[Path, bytes]:
    resolved = _input_file(path, label=label)
    try:
        return resolved, resolved.read_bytes()
    except OSError as error:
        raise ForgejoPublicationStateEvidenceError(f"{label} cannot be read") from error


def _file_sha256_and_size(path: Path, *, label: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as error:
        raise ForgejoPublicationStateEvidenceError(f"{label} cannot be read") from error
    return digest.hexdigest(), size


def _json_object(
    path: str | Path,
    *,
    label: str,
) -> tuple[Path, bytes, dict[str, Any]]:
    resolved, raw = _input_bytes(path, label=label)
    try:
        value = loads_strict(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ForgejoPublicationStateEvidenceError(
            f"{label} must be strict UTF-8 JSON"
        ) from error
    if not isinstance(value, dict):
        raise ForgejoPublicationStateEvidenceError(f"{label} must be a JSON object")
    return resolved, raw, value


def _require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ForgejoPublicationStateEvidenceError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return value


def bind_exact_bundle(
    *,
    manifest_path: str | Path,
    forgejo_archive_path: str | Path,
    webhook_sink_archive_path: str | Path,
) -> dict[str, Any]:
    manifest_source, manifest_raw, manifest = _json_object(
        manifest_path,
        label="bundle manifest",
    )
    forgejo_source = _input_file(
        forgejo_archive_path,
        label="Forgejo bundle archive",
    )
    sink_source = _input_file(
        webhook_sink_archive_path,
        label="webhook-sink bundle archive",
    )
    if len({manifest_source, forgejo_source, sink_source}) != 3:
        raise ForgejoPublicationStateEvidenceError(
            "bundle inputs must be three distinct files"
        )
    if set(manifest) != _BUNDLE_FIELDS:
        raise ForgejoPublicationStateEvidenceError(
            "bundle manifest fields are not exact"
        )
    if (
        manifest["schema_version"] != _BUNDLE_SCHEMA_VERSION
        or manifest["capture_mode"] != _BUNDLE_CAPTURE_MODE
    ):
        raise ForgejoPublicationStateEvidenceError(
            "bundle manifest does not describe an exact quiesced bundle"
        )
    expected_forgejo = _require_sha256(
        manifest["forgejo_sha256"],
        field="bundle manifest forgejo_sha256",
    )
    expected_sink = _require_sha256(
        manifest["webhook_sink_sha256"],
        field="bundle manifest webhook_sink_sha256",
    )
    observed_forgejo, forgejo_size = _file_sha256_and_size(
        forgejo_source,
        label="Forgejo bundle archive",
    )
    observed_sink, sink_size = _file_sha256_and_size(
        sink_source,
        label="webhook-sink bundle archive",
    )
    if observed_forgejo != expected_forgejo or observed_sink != expected_sink:
        raise ForgejoPublicationStateEvidenceError(
            "bundle archive content does not match bundle.json"
        )
    return {
        "manifest": deterministic_state_projection(manifest),
        "manifest_file_sha256": _sha256_bytes(manifest_raw),
        "forgejo_archive": {
            "sha256": observed_forgejo,
            "size_bytes": forgejo_size,
        },
        "webhook_sink_archive": {
            "sha256": observed_sink,
            "size_bytes": sink_size,
        },
    }


def _safe_archive_member_path(name: Any) -> str:
    if (
        not isinstance(name, str)
        or not name
        or "\x00" in name
        or "\\" in name
    ):
        raise ForgejoPublicationStateEvidenceError(
            "Forgejo archive contains an unsafe member path"
        )
    if name == ".":
        return ""
    candidate = name.removeprefix("./")
    if not candidate or candidate.startswith("/"):
        raise ForgejoPublicationStateEvidenceError(
            "Forgejo archive contains an unsafe member path"
        )
    parts = candidate.split("/")
    if (
        any(part in {"", ".", ".."} for part in parts)
        or re.fullmatch(r"[A-Za-z]:", parts[0]) is not None
    ):
        raise ForgejoPublicationStateEvidenceError(
            "Forgejo archive contains an unsafe member path"
        )
    return "/".join(parts)


def _archive_attachment_path(uuid: str) -> str:
    return f"gitea/attachments/{uuid[0]}/{uuid[1]}/{uuid}"


def _validated_asset_metadata(
    snapshot: dict[str, Any],
) -> dict[str, tuple[str, int, dict[str, Any]]]:
    expected: dict[str, tuple[str, int, dict[str, Any]]] = {}
    seen_uuids: set[str] = set()
    for field in (
        "target_release_assets",
        "protected_release_assets",
    ):
        assets = snapshot.get(field)
        if not isinstance(assets, list):
            raise ForgejoPublicationStateEvidenceError(
                f"native state {field} must be an array"
            )
        for index, asset in enumerate(assets):
            if not isinstance(asset, dict):
                raise ForgejoPublicationStateEvidenceError(
                    f"native state {field} contains non-object metadata"
                )
            asset_uuid = asset.get("uuid")
            if (
                not isinstance(asset_uuid, str)
                or _CANONICAL_UUID.fullmatch(asset_uuid) is None
            ):
                raise ForgejoPublicationStateEvidenceError(
                    f"native state {field} contains an invalid attachment UUID"
                )
            if asset_uuid in seen_uuids:
                raise ForgejoPublicationStateEvidenceError(
                    "native state contains a duplicate attachment UUID"
                )
            seen_uuids.add(asset_uuid)
            size = asset.get("size")
            if (
                not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
            ):
                raise ForgejoPublicationStateEvidenceError(
                    f"native state {field} contains an invalid attachment size"
                )
            expected[_archive_attachment_path(asset_uuid)] = (
                field,
                index,
                asset,
            )
    return expected


def enrich_snapshot_assets_from_bound_archive(
    snapshot: dict[str, Any],
    forgejo_archive_path: str | Path,
    *,
    archive_sha256: str,
    archive_size_bytes: int,
) -> dict[str, Any]:
    """Hash attachment bytes from a bound native archive without HTTP reads."""

    if not isinstance(snapshot, dict):
        raise ForgejoPublicationStateEvidenceError(
            "native metadata snapshot must be an object"
        )
    expected_sha256 = _require_sha256(
        archive_sha256,
        field="bound Forgejo archive sha256",
    )
    if (
        not isinstance(archive_size_bytes, int)
        or isinstance(archive_size_bytes, bool)
        or archive_size_bytes < 0
    ):
        raise ForgejoPublicationStateEvidenceError(
            "bound Forgejo archive size must be a non-negative integer"
        )
    source = _input_file(
        forgejo_archive_path,
        label="Forgejo bundle archive",
    )
    result = deepcopy(snapshot)
    expected = _validated_asset_metadata(result)
    observed: set[str] = set()
    try:
        with source.open("rb") as raw:
            digest = hashlib.sha256()
            observed_archive_size = 0
            while chunk := raw.read(1024 * 1024):
                digest.update(chunk)
                observed_archive_size += len(chunk)
            if (
                digest.hexdigest() != expected_sha256
                or observed_archive_size != archive_size_bytes
            ):
                raise ForgejoPublicationStateEvidenceError(
                    "Forgejo archive changed after its bundle binding"
                )
            raw.seek(0)
            with tarfile.open(fileobj=raw, mode="r:gz") as archive:
                for member in archive:
                    member_path = _safe_archive_member_path(member.name)
                    if member_path not in expected:
                        continue
                    if member_path in observed:
                        raise ForgejoPublicationStateEvidenceError(
                            "Forgejo archive contains a duplicate attachment member"
                        )
                    if not member.isfile():
                        raise ForgejoPublicationStateEvidenceError(
                            "Forgejo archive attachment member is not a regular file"
                        )
                    field, index, asset = expected[member_path]
                    expected_size = int(asset["size"])
                    if member.size != expected_size:
                        raise ForgejoPublicationStateEvidenceError(
                            "Forgejo archive attachment size does not match "
                            "native metadata"
                        )
                    content = archive.extractfile(member)
                    if content is None:
                        raise ForgejoPublicationStateEvidenceError(
                            "Forgejo archive attachment member cannot be read"
                        )
                    content_digest = hashlib.sha256()
                    content_size = 0
                    while chunk := content.read(1024 * 1024):
                        content_digest.update(chunk)
                        content_size += len(chunk)
                    if content_size != expected_size:
                        raise ForgejoPublicationStateEvidenceError(
                            "Forgejo archive attachment bytes are truncated"
                        )
                    result[field][index] = {
                        **asset,
                        "content_sha256": content_digest.hexdigest(),
                        "content_size": content_size,
                    }
                    observed.add(member_path)
    except ForgejoPublicationStateEvidenceError:
        raise
    except (OSError, EOFError, tarfile.TarError) as error:
        raise ForgejoPublicationStateEvidenceError(
            "Forgejo archive cannot be read as a safe gzip tar"
        ) from error
    missing = sorted(set(expected) - observed)
    if missing:
        raise ForgejoPublicationStateEvidenceError(
            "Forgejo archive is missing attachment members: "
            + ", ".join(missing)
        )
    return result


def _prefix_identity(
    prefix: dict[str, Any],
    *,
    prefix_raw: bytes,
) -> dict[str, str]:
    scenario_id = prefix.get("scenario_id")
    instance_spec_sha256 = prefix.get("instance_spec_sha256")
    owner = prefix.get("owner")
    repository = prefix.get("repository")
    release_tag = prefix.get("release_tag")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise ForgejoPublicationStateEvidenceError(
            "prefix scenario_id must be non-empty"
        )
    _require_sha256(
        instance_spec_sha256,
        field="prefix instance_spec_sha256",
    )
    for field, value in (
        ("owner", owner),
        ("repository", repository),
        ("release_tag", release_tag),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ForgejoPublicationStateEvidenceError(
                f"prefix {field} must be non-empty"
            )
    return {
        "scenario_id": scenario_id,
        "instance_spec_sha256": instance_spec_sha256,
        "prefix_file_sha256": _sha256_bytes(prefix_raw),
        "release_tag": release_tag,
    }


def _require_variant(variant_id: str) -> None:
    if variant_id not in FORGEJO_PUBLICATION_VARIANTS:
        raise ForgejoPublicationStateEvidenceError(
            "variant_id is not a Forgejo publication variant"
        )


def _environment_from_inputs(
    credentials: dict[str, Any],
    prefix: dict[str, Any],
) -> ForgejoPublicationEnvironment:
    required = (
        "base_url",
        "token",
        "web_base_url",
        "username",
        "password",
    )
    for field in required:
        value = credentials.get(field)
        if not isinstance(value, str) or not value:
            raise ForgejoPublicationStateEvidenceError(
                f"credentials {field} must be non-empty"
            )
    return ForgejoPublicationEnvironment(
        api=ForgejoAPI(
            base_url=credentials["base_url"],
            token=credentials["token"],
        ),
        web=ForgejoWebSession(
            base_url=credentials["web_base_url"],
            username=credentials["username"],
            password=credentials["password"],
        ),
        prefix=prefix,
    )


def _validated_native_state(
    snapshot: Any,
) -> tuple[dict[str, Any], str]:
    if not isinstance(snapshot, dict):
        raise ForgejoPublicationStateEvidenceError(
            "ForgejoPublicationEnvironment.snapshot() must return an object"
        )
    projection = deterministic_state_projection(snapshot)
    return projection, canonical_state_fingerprint(projection)


def build_reset_state_evidence(
    *,
    prefix: dict[str, Any],
    prefix_raw: bytes,
    variant_id: str,
    bundle: dict[str, Any],
    native_snapshot: dict[str, Any],
    expected_projection_raw: bytes | None = None,
    expected_projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_variant(variant_id)
    identity = _prefix_identity(prefix, prefix_raw=prefix_raw)
    state_projection, state_fingerprint = _validated_native_state(native_snapshot)
    if (expected_projection_raw is None) is not (expected_projection is None):
        raise ForgejoPublicationStateEvidenceError(
            "expected projection content and bytes must be supplied together"
        )
    expected_binding: dict[str, Any]
    if expected_projection is None:
        expected_binding = {
            "provided": False,
            "file_sha256": None,
            "state_fingerprint": None,
            "exact_match": None,
        }
        reset_verified = False
    else:
        normalized_expected = deterministic_state_projection(expected_projection)
        exact_match = normalized_expected == state_projection
        expected_binding = {
            "provided": True,
            "file_sha256": _sha256_bytes(expected_projection_raw or b""),
            "state_fingerprint": canonical_state_fingerprint(normalized_expected),
            "exact_match": exact_match,
        }
        reset_verified = exact_match
    return {
        "schema_version": "1.0",
        "artifact_type": "forgejo_publication_native_state_projection",
        **identity,
        "variant_id": variant_id,
        "phase": "reset",
        "bundle_manifest_file_sha256": bundle["manifest_file_sha256"],
        "bundle": bundle,
        "state_projection": state_projection,
        "state_fingerprint": state_fingerprint,
        "expected_projection": expected_binding,
        "expected_projection_establishment": {
            "performed": False,
            "file_sha256": None,
            "state_fingerprint": None,
        },
        "reset_verified": reset_verified,
    }


def _reset_binding(
    reset: dict[str, Any],
    *,
    reset_raw: bytes,
    identity: dict[str, str],
    variant_id: str,
) -> dict[str, str]:
    if (
        reset.get("schema_version") != "1.0"
        or reset.get("artifact_type") != "forgejo_publication_native_state_projection"
        or reset.get("scenario_id") != identity["scenario_id"]
        or reset.get("instance_spec_sha256") != identity["instance_spec_sha256"]
        or reset.get("prefix_file_sha256") != identity["prefix_file_sha256"]
        or reset.get("release_tag") != identity["release_tag"]
        or reset.get("variant_id") != variant_id
        or reset.get("phase") != "reset"
        or reset.get("reset_verified") is not True
    ):
        raise ForgejoPublicationStateEvidenceError(
            "reset evidence is not a verified reset for this boundary"
        )
    expected = reset.get("expected_projection")
    if (
        not isinstance(expected, dict)
        or expected.get("provided") is not True
        or expected.get("exact_match") is not True
    ):
        raise ForgejoPublicationStateEvidenceError(
            "reset evidence lacks an exact expected-state comparison"
        )
    projection = reset.get("state_projection")
    if not isinstance(projection, dict):
        raise ForgejoPublicationStateEvidenceError(
            "reset evidence lacks a complete native state projection"
        )
    fingerprint = canonical_state_fingerprint(
        deterministic_state_projection(projection)
    )
    if reset.get("state_fingerprint") != fingerprint:
        raise ForgejoPublicationStateEvidenceError(
            "reset evidence state fingerprint is invalid"
        )
    _require_sha256(
        expected.get("file_sha256"),
        field="reset expected projection file_sha256",
    )
    if expected.get("state_fingerprint") != fingerprint:
        raise ForgejoPublicationStateEvidenceError(
            "reset expected projection fingerprint is invalid"
        )
    manifest_sha256 = _require_sha256(
        reset.get("bundle_manifest_file_sha256"),
        field="reset bundle_manifest_file_sha256",
    )
    bundle = reset.get("bundle")
    if (
        not isinstance(bundle, dict)
        or bundle.get("manifest_file_sha256") != manifest_sha256
        or not isinstance(bundle.get("manifest"), dict)
        or set(bundle["manifest"]) != _BUNDLE_FIELDS
        or bundle["manifest"].get("schema_version") != _BUNDLE_SCHEMA_VERSION
        or bundle["manifest"].get("capture_mode") != _BUNDLE_CAPTURE_MODE
    ):
        raise ForgejoPublicationStateEvidenceError(
            "reset evidence has an invalid bundle binding"
        )
    forgejo_sha256 = _require_sha256(
        bundle["manifest"].get("forgejo_sha256"),
        field="reset bundle manifest forgejo_sha256",
    )
    sink_sha256 = _require_sha256(
        bundle["manifest"].get("webhook_sink_sha256"),
        field="reset bundle manifest webhook_sink_sha256",
    )
    for field, expected_sha256 in (
        ("forgejo_archive", forgejo_sha256),
        ("webhook_sink_archive", sink_sha256),
    ):
        archive = bundle.get(field)
        if (
            not isinstance(archive, dict)
            or archive.get("sha256") != expected_sha256
            or not isinstance(archive.get("size_bytes"), int)
            or isinstance(archive.get("size_bytes"), bool)
            or archive["size_bytes"] < 0
        ):
            raise ForgejoPublicationStateEvidenceError(
                f"reset evidence has an invalid {field} binding"
            )
    return {
        "reset_snapshot_sha256": _sha256_bytes(reset_raw),
        "reset_state_fingerprint": fingerprint,
        "reset_bundle_manifest_file_sha256": manifest_sha256,
    }


def _failure_report_variant(report: dict[str, Any]) -> Any:
    legacy = report.get("variant")
    canonical = report.get("variant_id")
    if legacy is not None and canonical is not None and legacy != canonical:
        raise ForgejoPublicationStateEvidenceError(
            "failure report has conflicting variant identities"
        )
    return canonical if canonical is not None else legacy


def _asset_without_capture_fields(asset: Any) -> Any:
    if not isinstance(asset, dict):
        return asset
    return {
        key: value
        for key, value in asset.items()
        if key not in {"content_sha256", "content_size"}
    }


def _validate_failure_state(
    report: dict[str, Any],
    *,
    report_raw: bytes,
    identity: dict[str, str],
    variant_id: str,
    state_projection: dict[str, Any],
) -> dict[str, Any]:
    if (
        report.get("scenario_id") != identity["scenario_id"]
        or report.get("instance_spec_sha256") != identity["instance_spec_sha256"]
        or _failure_report_variant(report) != variant_id
    ):
        raise ForgejoPublicationStateEvidenceError(
            "failure report identity does not match boundary"
        )
    checks = report.get("checks")
    if (
        report.get("passed") is not True
        or not isinstance(checks, dict)
        or not checks
        or any(value is not True for value in checks.values())
    ):
        raise ForgejoPublicationStateEvidenceError(
            "failure report did not pass all boundary checks"
        )
    visible_failure = report.get("visible_failure")
    if (
        not isinstance(visible_failure, dict)
        or visible_failure.get("ok") is not False
        or not isinstance(visible_failure.get("error"), str)
        or not visible_failure["error"].strip()
    ):
        raise ForgejoPublicationStateEvidenceError(
            "failure report lacks a non-empty visible error"
        )
    surface_result = report.get("surface_result")
    if not isinstance(surface_result, str) or not surface_result.strip():
        raise ForgejoPublicationStateEvidenceError(
            "failure report surface_result must be non-empty"
        )
    if (
        not isinstance(report.get("harness_error_type"), str)
        or not report["harness_error_type"].strip()
    ):
        raise ForgejoPublicationStateEvidenceError(
            "failure report lacks the observed harness error type"
        )
    boundary = report.get("failure_boundary_evidence")
    if not isinstance(boundary, dict):
        raise ForgejoPublicationStateEvidenceError(
            "failure report lacks failure_boundary_evidence"
        )
    releases = state_projection.get("releases")
    if not isinstance(releases, list):
        raise ForgejoPublicationStateEvidenceError("native state lacks releases")
    target_release = next(
        (
            release
            for release in releases
            if isinstance(release, dict)
            and release.get("tag_name") == identity["release_tag"]
        ),
        None,
    )
    captured_release = boundary.get("release")
    if captured_release is not None and (
        not isinstance(captured_release, dict)
        or captured_release.get("tag_name") != identity["release_tag"]
    ):
        raise ForgejoPublicationStateEvidenceError(
            "failure report captured the wrong target Release"
        )
    current_assets = [
        _asset_without_capture_fields(asset)
        for asset in state_projection.get("target_release_assets", [])
    ]
    comparisons = {
        "release": target_release,
        "assets": current_assets,
        "coordinator_history": state_projection.get("coordinator_history"),
        "provenance_history": state_projection.get("provenance_history"),
        "external_deliveries": state_projection.get("external_deliveries"),
    }
    mismatches = [
        field
        for field, current in comparisons.items()
        if deterministic_state_projection(boundary.get(field))
        != deterministic_state_projection(current)
    ]
    if mismatches:
        raise ForgejoPublicationStateEvidenceError(
            "failure report does not describe the captured native state: "
            + ", ".join(sorted(mismatches))
        )
    return {
        "failure_report_file_sha256": _sha256_bytes(report_raw),
        "surface_result": surface_result,
        "visible_failure": deterministic_state_projection(visible_failure),
        "harness_error_type": report["harness_error_type"],
    }


def build_boundary_state_evidence(
    *,
    prefix: dict[str, Any],
    prefix_raw: bytes,
    variant_id: str,
    bundle: dict[str, Any],
    native_snapshot: dict[str, Any],
    reset_raw: bytes,
    reset: dict[str, Any],
    failure_report_raw: bytes,
    failure_report: dict[str, Any],
) -> dict[str, Any]:
    _require_variant(variant_id)
    identity = _prefix_identity(prefix, prefix_raw=prefix_raw)
    reset_binding = _reset_binding(
        reset,
        reset_raw=reset_raw,
        identity=identity,
        variant_id=variant_id,
    )
    state_projection, state_fingerprint = _validated_native_state(native_snapshot)
    failure_binding = _validate_failure_state(
        failure_report,
        report_raw=failure_report_raw,
        identity=identity,
        variant_id=variant_id,
        state_projection=state_projection,
    )
    return {
        "schema_version": "1.0",
        "artifact_type": "forgejo_publication_native_state_projection",
        **identity,
        "variant_id": variant_id,
        "phase": "boundary",
        **reset_binding,
        **failure_binding,
        "bundle_manifest_file_sha256": bundle["manifest_file_sha256"],
        "bundle": bundle,
        "state_projection": state_projection,
        "state_fingerprint": state_fingerprint,
        "boundary_validation_passed": True,
    }


def capture_forgejo_publication_state_evidence(
    *,
    phase: str,
    credentials_path: str | Path,
    prefix_path: str | Path,
    variant_id: str,
    bundle_manifest_path: str | Path,
    forgejo_archive_path: str | Path,
    webhook_sink_archive_path: str | Path,
    expected_projection_path: str | Path | None = None,
    establish_expected_projection: bool = False,
    reset_evidence_path: str | Path | None = None,
    failure_report_path: str | Path | None = None,
    environment_factory: Callable[
        [dict[str, Any], dict[str, Any]],
        ForgejoPublicationEnvironment,
    ] = _environment_from_inputs,
) -> dict[str, Any]:
    if phase not in {"reset", "boundary"}:
        raise ForgejoPublicationStateEvidenceError("phase must be reset or boundary")
    if phase == "reset" and (
        reset_evidence_path is not None or failure_report_path is not None
    ):
        raise ForgejoPublicationStateEvidenceError(
            "reset phase must not receive boundary-only inputs"
        )
    if phase == "reset" and (
        expected_projection_path is not None and establish_expected_projection
    ):
        raise ForgejoPublicationStateEvidenceError(
            "expected projection and establishment mode are mutually exclusive"
        )
    if phase == "boundary" and (
        reset_evidence_path is None
        or failure_report_path is None
        or expected_projection_path is not None
        or establish_expected_projection
    ):
        raise ForgejoPublicationStateEvidenceError(
            "boundary phase requires reset evidence and failure report only"
        )
    _, _, credentials = _json_object(
        credentials_path,
        label="credentials",
    )
    _, prefix_raw, prefix = _json_object(prefix_path, label="prefix")
    bundle = bind_exact_bundle(
        manifest_path=bundle_manifest_path,
        forgejo_archive_path=forgejo_archive_path,
        webhook_sink_archive_path=webhook_sink_archive_path,
    )
    environment = environment_factory(credentials, prefix)
    metadata_snapshot = getattr(environment, "snapshot_metadata", None)
    native_snapshot = (
        metadata_snapshot()
        if callable(metadata_snapshot)
        else environment.snapshot()
    )
    native_snapshot = enrich_snapshot_assets_from_bound_archive(
        native_snapshot,
        forgejo_archive_path,
        archive_sha256=bundle["forgejo_archive"]["sha256"],
        archive_size_bytes=bundle["forgejo_archive"]["size_bytes"],
    )
    if phase == "reset":
        expected_raw: bytes | None = None
        expected: dict[str, Any] | None = None
        if expected_projection_path is not None:
            _, expected_raw, expected = _json_object(
                expected_projection_path,
                label="expected projection",
            )
        return build_reset_state_evidence(
            prefix=prefix,
            prefix_raw=prefix_raw,
            variant_id=variant_id,
            bundle=bundle,
            native_snapshot=native_snapshot,
            expected_projection_raw=expected_raw,
            expected_projection=expected,
        )
    _, reset_raw, reset = _json_object(
        reset_evidence_path,
        label="reset evidence",
    )
    _, failure_raw, failure = _json_object(
        failure_report_path,
        label="failure report",
    )
    return build_boundary_state_evidence(
        prefix=prefix,
        prefix_raw=prefix_raw,
        variant_id=variant_id,
        bundle=bundle,
        native_snapshot=native_snapshot,
        reset_raw=reset_raw,
        reset=reset,
        failure_report_raw=failure_raw,
        failure_report=failure,
    )


def _render_deterministic_json(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            deterministic_state_projection(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise ForgejoPublicationStateEvidenceError(
            "evidence cannot be rendered as deterministic JSON"
        ) from error
    return (rendered + "\n").encode("utf-8")


def _write_atomic_immutable(
    path: str | Path,
    raw: bytes,
    *,
    label: str,
) -> Path:
    output = Path(path)
    if ".." in output.parts:
        raise ForgejoPublicationStateEvidenceError(
            f"{label} path must not contain parent traversal"
        )
    _reject_symlink_path(output.parent, label=f"{label} path")
    if output.exists():
        raise ForgejoPublicationStateEvidenceError(f"{label} path already exists")
    temporary: Path | None = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        _reject_symlink_path(output.parent, label=f"{label} path")
        resolved = output.resolve(strict=False)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            dir=resolved.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, resolved)
        except FileExistsError as error:
            raise ForgejoPublicationStateEvidenceError(
                f"{label} path already exists"
            ) from error
    except ForgejoPublicationStateEvidenceError:
        raise
    except OSError as error:
        raise ForgejoPublicationStateEvidenceError(
            f"{label} path cannot be written atomically"
        ) from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return resolved


def establish_expected_projection(
    path: str | Path,
    reset_payload: dict[str, Any],
) -> dict[str, Any]:
    expected = reset_payload.get("expected_projection")
    establishment = reset_payload.get("expected_projection_establishment")
    if (
        reset_payload.get("phase") != "reset"
        or reset_payload.get("reset_verified") is not False
        or not isinstance(expected, dict)
        or expected.get("provided") is not False
        or not isinstance(establishment, dict)
        or establishment.get("performed") is not False
    ):
        raise ForgejoPublicationStateEvidenceError(
            "only an unverified reset capture may establish a projection"
        )
    projection = reset_payload.get("state_projection")
    if not isinstance(projection, dict):
        raise ForgejoPublicationStateEvidenceError(
            "reset capture lacks a complete state projection"
        )
    raw = _render_deterministic_json(projection)
    _write_atomic_immutable(
        path,
        raw,
        label="expected projection",
    )
    result = deepcopy(reset_payload)
    result["expected_projection_establishment"] = {
        "performed": True,
        "file_sha256": _sha256_bytes(raw),
        "state_fingerprint": canonical_state_fingerprint(projection),
    }
    # Establishing the comparison target is not itself reset verification.
    result["reset_verified"] = False
    return result


def write_state_evidence(
    path: str | Path,
    payload: dict[str, Any],
) -> Path:
    return _write_atomic_immutable(
        path,
        _render_deterministic_json(payload),
        label="output",
    )


__all__ = [
    "ForgejoPublicationStateEvidenceError",
    "bind_exact_bundle",
    "build_boundary_state_evidence",
    "build_reset_state_evidence",
    "canonical_state_fingerprint",
    "capture_forgejo_publication_state_evidence",
    "deterministic_state_projection",
    "enrich_snapshot_assets_from_bound_archive",
    "establish_expected_projection",
    "write_state_evidence",
]
