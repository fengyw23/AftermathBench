from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.native_freeze import validate_usage_ledger


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a non-sensitive hidden-evaluation lifecycle receipt."
    )
    parser.add_argument("--commitment", type=Path, required=True)
    parser.add_argument("--usage-ledger", type=Path, required=True)
    parser.add_argument("--model-summary", type=Path)
    parser.add_argument("--provider-profile", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--evaluation-run-id", required=True)
    parser.add_argument("--freeze-run-id", required=True)
    parser.add_argument("--freeze-artifact-id", required=True)
    parser.add_argument("--freeze-artifact-digest", required=True)
    parser.add_argument("--ciphertext-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    commitment = _read(args.commitment)
    ledger = _read(args.usage_ledger)
    ledger_failures = list(validate_usage_ledger(ledger))
    events = ledger.get("events", [])
    event_names = [str(item.get("event", "")) for item in events]
    model_summary = (
        _read(args.model_summary)
        if args.model_summary is not None and args.model_summary.is_file()
        else None
    )
    aggregate = None
    if model_summary is not None:
        aggregate = {
            "completed_runs": int(model_summary.get("completed_runs", 0)),
            "run_error_count": len(model_summary.get("run_errors", [])),
            "task_pass_rate": float(model_summary.get("task_pass_rate", 0.0)),
            "matched_group_count": int(
                model_summary.get("matched_group_count", 0)
            ),
            "matched_group_success_rate": float(
                model_summary.get("matched_group_success_rate", 0.0)
            ),
            "component_pass_rates": model_summary.get(
                "component_pass_rates", {}
            ),
            "failure_type_counts": model_summary.get(
                "failure_type_counts", {}
            ),
            "execution_control_counts": model_summary.get(
                "execution_control_counts", {}
            ),
        }
    payload = {
        "schema_version": "1.0",
        "lifecycle_status": event_names[-1] if event_names else "missing",
        "scenario_id": commitment.get("scenario_id"),
        "public_commitment_sha256": commitment.get(
            "public_commitment_sha256"
        ),
        "freeze_provenance": {
            "run_id": int(args.freeze_run_id),
            "artifact_id": int(args.freeze_artifact_id),
            "artifact_digest": args.freeze_artifact_digest,
            "ciphertext_sha256": args.ciphertext_sha256,
        },
        "evaluation": {
            "run_id": int(args.evaluation_run_id),
            "provider_profile": args.provider_profile,
            "model": args.model,
            "aggregate": aggregate,
        },
        "usage_ledger": {
            "integrity_passed": not ledger_failures,
            "integrity_failures": ledger_failures,
            "events": event_names,
            "head_event_sha256": ledger.get("head_event_sha256"),
        },
        "raw_hidden_bundle_published": False,
        "raw_model_trajectories_published": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario_id": payload["scenario_id"],
                "lifecycle_status": payload["lifecycle_status"],
                "completed_runs": (
                    aggregate["completed_runs"] if aggregate else 0
                ),
                "task_pass_rate": (
                    aggregate["task_pass_rate"] if aggregate else None
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
