from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_package_provenance_recovery import (
    ForgejoPackageProvenanceEnvironment,
    evaluate_forgejo_package_provenance_recovery,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


BASELINES = (
    "no_op",
    "blind_full_publish",
    "assume_package_exists",
    "metadata_only",
    "replay_all_failed",
    "close_only",
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _call(
    environment: ForgejoPackageProvenanceEnvironment,
    tool: str,
    **arguments: Any,
) -> bool:
    return bool(environment.invoke(tool, **arguments).get("ok"))


def _create_release(
    environment: ForgejoPackageProvenanceEnvironment,
    prefix: dict[str, Any],
) -> bool:
    return _call(
        environment,
        "create_package_index_release",
        tag=prefix["package_index_release_tag"],
        target=prefix["base_branch"],
        title=prefix["package_index_release_title"],
        body=prefix["package_index_release_body"],
    )


def _close(
    environment: ForgejoPackageProvenanceEnvironment,
    prefix: dict[str, Any],
) -> None:
    _call(
        environment,
        "close_milestone",
        milestone_id=prefix["milestone_id"],
    )
    for index in prefix["tracking_issue_indexes"]:
        _call(environment, "close_issue", index=index)


def _blind_upload(
    environment: ForgejoPackageProvenanceEnvironment,
    prefix: dict[str, Any],
    *,
    roles: set[str] | None = None,
) -> bool:
    for item in prefix["expected_package_files"]:
        if roles is not None and item["role"] not in roles:
            continue
        if not _call(
            environment,
            "upload_package_file_from_repository",
            source_path=item["source_path"],
            filename=item["name"],
            ref=prefix["base_branch"],
        ):
            return False
    return True


def execute(
    baseline: str,
    environment: ForgejoPackageProvenanceEnvironment,
    prefix: dict[str, Any],
) -> None:
    if baseline == "no_op":
        return
    if baseline == "blind_full_publish":
        if _blind_upload(environment, prefix):
            _create_release(environment, prefix)
            _close(environment, prefix)
        return
    if baseline == "assume_package_exists":
        if _create_release(environment, prefix):
            _close(environment, prefix)
        return
    if baseline == "metadata_only":
        if _blind_upload(
            environment,
            prefix,
            roles={"checksum", "sbom", "signature"},
        ):
            _create_release(environment, prefix)
            _close(environment, prefix)
        return
    if baseline == "replay_all_failed":
        for field in ("coordinator_hook_id", "provenance_hook_id"):
            history = environment.invoke(
                "get_webhook_history", hook_id=prefix[field]
            )
            if not history.get("ok"):
                continue
            for item in history["result"]:
                if item.get("status") == "failed":
                    _call(
                        environment,
                        "replay_webhook",
                        hook_id=prefix[field],
                        delivery_uuid=item["uuid"],
                    )
        _close(environment, prefix)
        return
    if baseline == "close_only":
        _close(environment, prefix)
        return
    raise ValueError(f"unknown baseline: {baseline}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--baseline", choices=BASELINES, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    boundary = _read(args.boundary)
    environment = ForgejoPackageProvenanceEnvironment(
        api=ForgejoAPI(
            base_url=credentials["base_url"], token=credentials["token"]
        ),
        web=ForgejoWebSession(
            base_url=credentials["web_base_url"],
            username=credentials["username"],
            password=credentials["password"],
        ),
        prefix=prefix,
    )
    execute(args.baseline, environment, prefix)
    final_state = environment.snapshot()
    evaluation = evaluate_forgejo_package_provenance_recovery(
        final_state, prefix=prefix
    )
    payload = {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "variant": boundary["variant"],
        "baseline": args.baseline,
        "events": environment.event_log(),
        "evaluation": {
            "passed": evaluation.passed,
            "components": evaluation.components,
            "failures": list(evaluation.failures),
        },
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
                "baseline": args.baseline,
                "variant": boundary["variant"],
                "passed": evaluation.passed,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
