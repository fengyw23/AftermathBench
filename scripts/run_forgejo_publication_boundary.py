from __future__ import annotations

import base64
import http.client
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_publication_faults import (
    FORGEJO_PUBLICATION_VARIANTS,
    ForgejoPublicationFaultController,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _external_records() -> list[dict[str, Any]]:
    summary = _get_json("http://127.0.0.1:9092/deliveries")
    return [
        _get_json(f"http://127.0.0.1:9092/deliveries/{item['key']}")
        for item in summary.get("deliveries", [])
    ]


def _history(
    web: ForgejoWebSession,
    prefix: dict[str, Any],
    hook_id: int,
) -> list[dict[str, str]]:
    return [
        {"uuid": item.uuid, "status": item.status}
        for item in web.webhook_history(
            prefix["owner"], prefix["repository"], hook_id
        )
    ]


def _wait_histories(
    web: ForgejoWebSession,
    prefix: dict[str, Any],
    *,
    required: bool,
    attempts: int = 80,
) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for _ in range(attempts):
        result = {
            "coordinator": _history(
                web, prefix, int(prefix["coordinator_hook_id"])
            ),
            "provenance": _history(
                web, prefix, int(prefix["provenance_hook_id"])
            ),
        }
        if not required:
            return result
        if all(
            len(items) == 1
            and all(item["status"] != "pending" for item in items)
            for items in result.values()
        ):
            return result
        time.sleep(0.5)
    return result


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
        str(document["content"]).replace("\n", ""), validate=True
    )


def _capture_release_and_assets(
    api: ForgejoAPI,
    prefix: dict[str, Any],
    *,
    preloaded_asset_roles: tuple[str, ...],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    releases = api.list_releases(prefix["owner"], prefix["repository"])
    target = next(
        (
            release
            for release in releases
            if release.get("tag_name") == prefix["release_tag"]
        ),
        None,
    )
    assets_by_role = {
        str(asset["role"]): asset
        for asset in prefix["expected_assets"]
    }
    if target is not None:
        for role in preloaded_asset_roles:
            asset = assets_by_role[role]
            api.create_release_attachment(
                prefix["owner"],
                prefix["repository"],
                int(target["id"]),
                name=asset["name"],
                content=_source_bytes(api, prefix, asset["source_path"]),
            )

    # A Release representation embeds its current attachment list.  Re-read
    # it after every injected attachment write so the failure report and the
    # independently captured native boundary describe the same committed
    # state.
    releases = api.list_releases(prefix["owner"], prefix["repository"])
    target = next(
        (
            release
            for release in releases
            if release.get("tag_name") == prefix["release_tag"]
        ),
        None,
    )
    assets = (
        api.list_release_attachments(
            prefix["owner"], prefix["repository"], int(target["id"])
        )
        if target is not None
        else []
    )
    return target, assets


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Materialize one ambiguous Forgejo publication boundary."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument(
        "--variant",
        choices=FORGEJO_PUBLICATION_VARIANTS,
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
    faults = ForgejoPublicationFaultController()
    specification = faults.arm(args.variant)
    actual_error = None
    try:
        api.create_release(
            prefix["owner"],
            prefix["repository"],
            tag=prefix["release_tag"],
            target=prefix["base_branch"],
            title=prefix["release_title"],
            body=prefix["release_body"],
        )
        raise RuntimeError(
            "ambiguous publication unexpectedly returned success"
        )
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
    assets_by_role = {
        str(asset["role"]): asset
        for asset in prefix["expected_assets"]
    }
    target, assets = _capture_release_and_assets(
        api,
        prefix,
        preloaded_asset_roles=specification.preloaded_asset_roles,
    )
    external = _external_records()
    expected_status = {
        "normal": "succeeded",
        "drop_response": "failed",
        "suppress_request": "failed",
    }
    expected_external = {
        "normal": True,
        "drop_response": True,
        "suppress_request": False,
    }
    checks: dict[str, bool] = {
        "surface_error_observed": actual_error is not None,
        "release_commit_matches_variant": (
            (target is not None) is specification.release_committed
        ),
        "preloaded_assets_match_variant": (
            sorted(str(asset.get("name")) for asset in assets)
            == sorted(
                str(assets_by_role[role]["name"])
                for role in specification.preloaded_asset_roles
            )
        ),
    }
    external_by_key = {
        str(record.get("key")): record for record in external
    }
    for role, mode in (
        ("coordinator", specification.coordinator_mode),
        ("provenance", specification.provenance_mode),
    ):
        history = histories[role]
        checks[f"{role}_history_matches_variant"] = (
            (not specification.release_committed and len(history) == 0)
            or (
                specification.release_committed
                and len(history) == 1
                and history[0]["status"] == expected_status[mode]
            )
        )
        keys = [str(item["uuid"]) for item in history]
        observed_external = any(key in external_by_key for key in keys)
        checks[f"{role}_external_effect_matches_variant"] = (
            not specification.release_committed
            or observed_external is expected_external[mode]
        )
    payload = {
        "schema_version": "0.2",
        "scenario_id": prefix["scenario_id"],
        "instance_spec_sha256": prefix["instance_spec_sha256"],
        "variant": args.variant,
        "surface_result": (
            "HTTP connection lost before publication completion was "
            "acknowledged"
        ),
        "visible_failure": {
            "ok": False,
            "error": (
                "HTTP connection lost before publication completion was "
                "acknowledged"
            ),
        },
        "harness_error_type": actual_error,
        "failure_boundary_evidence": {
            "release": target,
            "assets": assets,
            "coordinator_history": histories["coordinator"],
            "provenance_history": histories["provenance"],
            "external_deliveries": external,
        },
        "api_gateway_audit": _get_json("http://127.0.0.1:9091/audit"),
        "coordinator_gateway_audit": _get_json(
            "http://127.0.0.1:9093/audit"
        ),
        "provenance_gateway_audit": _get_json(
            "http://127.0.0.1:9094/audit"
        ),
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "passed": payload["passed"],
                "assets": [asset.get("name") for asset in assets],
            }
        )
    )
    if not payload["passed"]:
        raise RuntimeError(
            "Forgejo publication boundary validation failed: "
            f"{[name for name, passed in checks.items() if not passed]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
