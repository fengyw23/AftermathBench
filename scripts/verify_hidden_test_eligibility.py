from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def verify_hidden_test_eligibility(
    *,
    scenario_path: Path,
    freeze_path: Path,
    usage_ledger_path: Path,
) -> dict[str, Any]:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    ledger = json.loads(usage_ledger_path.read_text(encoding="utf-8"))
    events = ledger.get("events", [])
    event_names = [
        str(item.get("event", ""))
        for item in events
        if isinstance(item, dict)
    ]
    frozen_events = [
        item
        for item in events
        if isinstance(item, dict) and item.get("event") == "frozen"
    ]
    frozen_commitment = (
        str(
            frozen_events[-1]
            .get("details", {})
            .get("public_commitment_sha256", "")
        )
        if frozen_events
        else ""
    )
    ledger_commitment = str(
        ledger.get("public_commitment_sha256", "")
    )
    bound_events = [
        item
        for item in events
        if isinstance(item, dict) and item.get("event") != "generated"
    ]
    observed = {
        "scenario_id": str(scenario.get("scenario_id", "")),
        "benchmark_split": str(scenario.get("benchmark_split", "")),
        "benchmark_tier": str(scenario.get("benchmark_tier", "")),
        "hidden_test_eligible": bool(
            scenario.get("evaluation_status", {}).get(
                "hidden_test_eligible",
                False,
            )
        ),
        "freeze_status": str(freeze.get("status", "")),
        "usage_events": event_names,
    }
    checks = {
        "scenario_ids_match": (
            observed["scenario_id"] == str(freeze.get("scenario_id", ""))
        ),
        "split_is_hidden_test": observed["benchmark_split"] == "hidden_test",
        "tier_is_hard": observed["benchmark_tier"] == "hard",
        "scenario_declares_hidden_eligibility": observed["hidden_test_eligible"],
        "freeze_is_active": observed["freeze_status"] == "active",
        "ledger_has_one_frozen_event": event_names.count("frozen") == 1,
        "ledger_sequence_is_valid_for_unseen_use": event_names
        in (["frozen"], ["generated", "frozen"]),
        "ledger_is_not_consumed": not any(
            event in {"evaluation_locked", "consumed", "retired"}
            for event in event_names
        ),
        "ledger_ends_at_frozen": bool(event_names)
        and event_names[-1] == "frozen",
        "ledger_commitment_matches_freeze": bool(frozen_commitment)
        and frozen_commitment
        == str(freeze.get("public_commitment_sha256", ""))
        and ledger_commitment == frozen_commitment
        and all(
            str(
                item.get("details", {}).get(
                    "public_commitment_sha256",
                    "",
                )
            )
            == frozen_commitment
            for item in bound_events
        ),
    }
    if not all(checks.values()):
        failures = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "scenario is not eligible for an unseen hidden-test claim: "
            f"{failures}; observed={observed}"
        )
    return {"checks": checks, "observed": observed}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Reject consumed or development scenarios before a hidden-test model run."
        )
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--usage-ledger", type=Path, required=True)
    args = parser.parse_args()
    result = verify_hidden_test_eligibility(
        scenario_path=args.scenario,
        freeze_path=args.freeze,
        usage_ledger_path=args.usage_ledger,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
