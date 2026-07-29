from __future__ import annotations

import argparse
import http.client
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_faults import (
    FORGEJO_FAULT_VARIANTS,
    ForgejoFaultController,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_history(
    session: ForgejoWebSession,
    prefix: dict[str, Any],
    *,
    required: bool,
    attempts: int = 60,
) -> list[dict[str, str]]:
    history = ()
    for _ in range(attempts):
        history = session.webhook_history(
            prefix["owner"],
            prefix["repository"],
            int(prefix["webhook_id"]),
        )
        if not required:
            break
        if history and all(
            delivery.status != "pending" for delivery in history
        ):
            break
        time.sleep(0.5)
    return [
        {"uuid": delivery.uuid, "status": delivery.status}
        for delivery in history
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument(
        "--variant",
        choices=FORGEJO_FAULT_VARIANTS,
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _load(args.credentials)
    prefix = _load(args.prefix)
    api = ForgejoAPI(
        base_url=credentials["base_url"],
        token=credentials["token"],
    )
    web = ForgejoWebSession(
        base_url=credentials["web_base_url"],
        username=credentials["username"],
        password=credentials["password"],
    )
    faults = ForgejoFaultController()
    faults.arm(args.variant)
    actual_error = None
    try:
        api.merge_pull_request(
            prefix["owner"],
            prefix["repository"],
            int(prefix["pull_request_index"]),
        )
        raise RuntimeError(
            "ambiguous merge unexpectedly returned a success response"
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

    committed = args.variant != "merge_request_not_reached"
    history = _wait_for_history(web, prefix, required=committed)
    faults.disarm_webhook_after_attempt()
    owner = prefix["owner"]
    repository = prefix["repository"]
    pull_index = int(prefix["pull_request_index"])
    issue_index = int(prefix["linked_issue_index"])
    pull = api.get_pull_request(owner, repository, pull_index)
    issue = api.get(
        f"/repos/{owner}/{repository}/issues/{issue_index}"
    )
    branch = api.get(
        f"/repos/{owner}/{repository}/branches/"
        f"{urllib.parse.quote(prefix['base_branch'], safe='')}"
    )
    external = _get_json("http://127.0.0.1:9092/deliveries")
    api_audit = _get_json("http://127.0.0.1:9091/audit")
    webhook_audit = _get_json("http://127.0.0.1:9093/audit")

    pull_merged = bool(pull.get("merged"))
    checks = {
        "surface_error_observed": actual_error is not None,
        "pull_commit_matches_variant": pull_merged is committed,
        "issue_state_matches_variant": (
            str(issue.get("state")) == ("closed" if committed else "open")
        ),
        "history_presence_matches_variant": bool(history) is committed,
        "branch_head_present": bool(
            branch.get("commit", {}).get("id")
        ),
    }
    expected_status = {
        "merge_committed_delivery_succeeded": "succeeded",
        "merge_committed_receiver_accepted_response_lost": "failed",
        "merge_committed_delivery_request_not_reached": "failed",
    }.get(args.variant)
    expected_external = {
        "merge_request_not_reached": 0,
        "merge_committed_delivery_succeeded": 1,
        "merge_committed_receiver_accepted_response_lost": 1,
        "merge_committed_delivery_request_not_reached": 0,
    }[args.variant]
    checks["history_status_matches_variant"] = (
        not committed
        or (
            len(history) == 1
            and history[0]["status"] == expected_status
        )
    )
    checks["external_effect_matches_variant"] = (
        int(external.get("unique_deliveries", -1)) == expected_external
    )
    payload = {
        "schema_version": "0.1",
        "scenario_id": "forgejo-pr-release-dev-001",
        "variant": args.variant,
        "surface_result": "HTTP connection lost before a success response",
        "harness_error_type": actual_error,
        "pull": {
            "state": pull.get("state"),
            "merged": pull_merged,
            "merge_base": pull.get("merge_base"),
        },
        "issue": {"state": issue.get("state")},
        "branch_head": branch.get("commit", {}).get("id"),
        "history": history,
        "external": external,
        "api_gateway_audit": api_audit,
        "webhook_gateway_audit": webhook_audit,
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"variant": args.variant, "passed": payload["passed"]}))
    if not payload["passed"]:
        raise RuntimeError(
            f"Forgejo merge boundary validation failed: "
            f"{[name for name, passed in checks.items() if not passed]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
