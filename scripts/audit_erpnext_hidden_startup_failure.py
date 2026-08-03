from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _last_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _restore_failure_class(path: Path) -> str:
    """Map a private restore log to a fixed, non-content-bearing category."""

    if not path.is_file():
        return "restore_not_started"
    text = path.read_text(encoding="utf-8", errors="replace")
    markers = (
        ("invalid_bundle_manifest", "invalid ERPNext native bundle manifest"),
        ("bundle_file_drift", "ERPNext native bundle file drift"),
        ("erpnext_readiness_timeout", "127.0.0.1:8080/api/method/ping"),
        ("gateway_readiness_timeout", "127.0.0.1:9091/audit"),
        ("remittance_readiness_timeout", "127.0.0.1:9092/health"),
        ("site_config_restore_command", "site_config.json"),
        ("database_import_command", "mariadb"),
        ("queue_state_restore_command", "redis-queue"),
        ("gateway_state_restore_command", "fault-gateway"),
        ("remittance_state_restore_command", "remittance"),
    )
    for category, marker in markers:
        if marker in text:
            return category
    if "Traceback (most recent call last)" in text:
        return "unclassified_python_failure"
    if text.strip():
        return "unclassified_restore_failure"
    return "empty_restore_log"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit only aggregate facts about a private ERPNext startup failure."
    )
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.private_root
    model = root / "model"
    restore_log = model / "repetition-01" / "credential-probe-restore.log"
    smoke = _last_json_object(model / "repetition-01" / "credential-smoke.log")
    manifests = []
    for path in sorted((root / "bundles").glob("boundary-*/bundle.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        manifests.append(value)
    versions = Counter(str(item.get("schema_version", "")) for item in manifests)
    site_config_bound = sum(
        int("site_config" in item.get("files", {})) for item in manifests
    )
    ledger = json.loads((root / "usage-ledger.json").read_text(encoding="utf-8"))
    events = [
        str(item.get("event", ""))
        for item in ledger.get("events", [])
        if isinstance(item, dict)
    ]
    attempt_logs = list(model.rglob("*-attempt-*.log")) if model.is_dir() else []
    trajectories = (
        [
            path
            for path in model.rglob("*.json")
            if path.name != "summary.json" and path.stat().st_size > 0
        ]
        if model.is_dir()
        else []
    )
    payload = {
        "schema_version": "1.0",
        "credential_smoke_present": smoke is not None,
        "credential_smoke_passed": (
            smoke.get("passed") if isinstance(smoke, dict) else None
        ),
        "credential_probe_restore_present": restore_log.is_file(),
        "credential_probe_restore_failure_class": _restore_failure_class(restore_log),
        "boundary_bundle_count": len(manifests),
        "bundle_schema_version_counts": dict(sorted(versions.items())),
        "site_config_bound_bundle_count": site_config_bound,
        "attempt_log_count": len(attempt_logs),
        "trajectory_count": len(trajectories),
        "usage_events": events,
        "raw_log_text_published": False,
        "variant_identities_published": False,
        "task_content_published": False,
        "credential_values_published": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
