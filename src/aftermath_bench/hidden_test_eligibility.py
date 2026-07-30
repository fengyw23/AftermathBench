from __future__ import annotations

from pathlib import Path
from typing import Any

from .native_freeze import validate_usage_ledger
from .strict_json import load_json_strict


def verify_hidden_test_eligibility(
    *,
    scenario_path: Path,
    freeze_path: Path,
    usage_ledger_path: Path,
) -> dict[str, Any]:
    """Reject a hidden instance once it is unfrozen or model-accessed.

    Full bundle verification is intentionally performed by the release
    manifest before this lifecycle check. This function checks that the three
    bound records agree and that the usage ledger has not advanced beyond its
    pre-model frozen state.
    """

    scenario = load_json_strict(scenario_path)
    freeze = load_json_strict(freeze_path)
    ledger = load_json_strict(usage_ledger_path)
    ledger_integrity_failures = validate_usage_ledger(ledger)
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
    ledger_commitment = str(ledger.get("public_commitment_sha256", ""))
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
        "scenario_declares_hidden_eligibility": observed[
            "hidden_test_eligible"
        ],
        "freeze_is_active": observed["freeze_status"] == "active",
        "ledger_has_one_frozen_event": event_names.count("frozen") == 1,
        "ledger_hash_chain_valid": not ledger_integrity_failures,
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


__all__ = ["verify_hidden_test_eligibility"]
