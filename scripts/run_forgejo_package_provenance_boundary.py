from __future__ import annotations

import base64
import http.client
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_package_provenance_faults import (
    FORGEJO_PACKAGE_PROVENANCE_VARIANTS,
    PACKAGE_PROVENANCE_VARIANTS,
    ForgejoPackageProvenanceFaultController,
)
from aftermath_bench.integrations.forgejo_package_provenance_recovery import (
    ForgejoPackageProvenanceEnvironment,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _source_bytes(
    api: ForgejoAPI,
    prefix: dict[str, Any],
    source_path: str,
) -> bytes:
    document = api.get_repository_content(
        prefix["owner"],
        prefix["repository"],
        path=source_path,
        ref=prefix["base_branch"],
    )
    return base64.b64decode(
        str(document["content"]).replace("\n", ""),
        validate=True,
    )


def _upload_role(
    api: ForgejoAPI,
    prefix: dict[str, Any],
    role: str,
) -> None:
    item = next(
        value
        for value in prefix["expected_package_files"]
        if value["role"] == role
    )
    api.upload_generic_package_file(
        prefix["owner"],
        name=prefix["package_name"],
        version=prefix["package_version"],
        filename=item["name"],
        content=_source_bytes(api, prefix, item["source_path"]),
    )


def _role_payload(
    api: ForgejoAPI,
    prefix: dict[str, Any],
    role: str,
) -> tuple[dict[str, Any], bytes]:
    item = next(
        value
        for value in prefix["expected_package_files"]
        if value["role"] == role
    )
    return item, _source_bytes(api, prefix, item["source_path"])


def _wait_histories(
    web: ForgejoWebSession,
    prefix: dict[str, Any],
    *,
    required: bool,
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for _ in range(80):
        result = {
            role: [
                {"uuid": item.uuid, "status": item.status}
                for item in web.webhook_history(
                    prefix["owner"],
                    prefix["repository"],
                    int(prefix[field]),
                )
            ]
            for role, field in (
                ("coordinator", "coordinator_hook_id"),
                ("provenance", "provenance_hook_id"),
            )
        }
        if not required or all(
            len(items) == 1
            and all(item["status"] != "pending" for item in items)
            for items in result.values()
        ):
            return result
        time.sleep(0.5)
    return result


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument(
        "--variant",
        choices=FORGEJO_PACKAGE_PROVENANCE_VARIANTS,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    api = ForgejoAPI(
        base_url=credentials["base_url"],
        token=credentials["token"],
    )
    web = ForgejoWebSession(
        base_url=credentials["web_base_url"],
        username=credentials["username"],
        password=credentials["password"],
    )
    faults = ForgejoPackageProvenanceFaultController()
    specification = PACKAGE_PROVENANCE_VARIANTS[args.variant]
    for role in specification.preloaded_file_roles:
        _upload_role(api, prefix, role)
    pending_binary: tuple[dict[str, Any], bytes] | None = None
    if specification.attempted_operation == "upload_binary":
        # Read the approved source before arming the one-shot transport seam.
        # The ambiguous failure must wrap the native package PUT itself, not
        # an earlier repository query used to construct the request body.
        pending_binary = _role_payload(api, prefix, "binary")
    specification = faults.arm(args.variant)
    actual_error: str | None = None
    try:
        if specification.attempted_operation == "upload_binary":
            assert pending_binary is not None
            item, content = pending_binary
            api.upload_generic_package_file(
                prefix["owner"],
                name=prefix["package_name"],
                version=prefix["package_version"],
                filename=item["name"],
                content=content,
            )
        else:
            api.create_release(
                prefix["owner"],
                prefix["repository"],
                tag=prefix["package_index_release_tag"],
                target=prefix["base_branch"],
                title=prefix["package_index_release_title"],
                body=prefix["package_index_release_body"],
            )
        raise RuntimeError("ambiguous package operation unexpectedly succeeded")
    except (
        ConnectionError,
        ConnectionResetError,
        http.client.RemoteDisconnected,
        TimeoutError,
        OSError,
    ) as error:
        actual_error = type(error).__name__
    finally:
        faults.disarm_api_after_surface_failure()

    histories = _wait_histories(
        web,
        prefix,
        required=specification.release_committed,
    )
    faults.disarm_webhooks_after_attempt()
    environment = ForgejoPackageProvenanceEnvironment(
        api=api,
        web=web,
        prefix=prefix,
    )
    state = environment.snapshot()
    target_roles = {
        item["name"]: item["role"]
        for item in prefix["expected_package_files"]
    }
    observed_roles = sorted(
        target_roles.get(str(item.get("name")), "unknown")
        for item in state["target_package_files"]
    )
    expected_roles = sorted(
        (
            (*specification.preloaded_file_roles, "binary")
            if specification.attempted_operation == "upload_binary"
            and specification.api_mode == "drop_response"
            else specification.preloaded_file_roles
        )
    )
    target_releases = [
        item
        for item in state["releases"]
        if item.get("tag_name") == prefix["package_index_release_tag"]
    ]
    api_gateway_audit = _get_json("http://127.0.0.1:9091/audit")
    expected_method = (
        "PUT"
        if specification.attempted_operation == "upload_binary"
        else "POST"
    )
    expected_path_fragment = (
        f"/api/packages/{prefix['owner']}/generic/"
        f"{prefix['package_name']}/{prefix['package_version']}/"
        if specification.attempted_operation == "upload_binary"
        else f"/api/v1/repos/{prefix['owner']}/{prefix['repository']}/releases"
    )
    ambiguous_events = [
        item
        for item in api_gateway_audit.get("events", [])
        if item.get("method") == expected_method
        and expected_path_fragment in str(item.get("path"))
        and item.get("mode") == specification.api_mode
    ]
    expected_outcome = (
        "upstream_completed_response_dropped"
        if specification.api_mode == "drop_response"
        else "request_suppressed"
    )
    checks = {
        "surface_error_observed": actual_error is not None,
        "ambiguous_write_hit_fault_seam_once": (
            len(ambiguous_events) == 1
            and ambiguous_events[0].get("outcome") == expected_outcome
        ),
        "package_files_match_variant": observed_roles == expected_roles,
        "release_commit_matches_variant": (
            len(target_releases) == (1 if specification.release_committed else 0)
        ),
        "histories_match_release_state": (
            all(len(items) == 1 for items in histories.values())
            if specification.release_committed
            else all(len(items) == 0 for items in histories.values())
        ),
    }
    payload = {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "instance_spec_sha256": prefix["instance_spec_sha256"],
        "variant": args.variant,
        "visible_failure": {
            "ok": False,
            "error": (
                "HTTP connection lost before package publication completion "
                "was acknowledged"
            ),
        },
        "harness_error_type": actual_error,
        "failure_boundary_evidence": state,
        "api_gateway_audit": api_gateway_audit,
        "coordinator_gateway_audit": _get_json("http://127.0.0.1:9093/audit"),
        "provenance_gateway_audit": _get_json("http://127.0.0.1:9094/audit"),
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "passed": payload["passed"],
                "observed_roles": observed_roles,
            }
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
