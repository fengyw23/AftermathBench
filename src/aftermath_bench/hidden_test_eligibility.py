from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .native_freeze import (
    append_usage_event,
    file_sha256,
    validate_usage_ledger,
)
from .strict_json import load_json_strict


@dataclass(frozen=True)
class HiddenEvaluationSession:
    """Proof that a hidden instance was locked before provider access."""

    scenario_id: str
    evaluation_id: str
    provider: str
    model: str
    execution_control: bool
    usage_ledger_path: Path
    lock_event_sha256: str


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
        "scenario_bytes_match_freeze": (
            file_sha256(scenario_path)
            == str(freeze.get("scenario_sha256", ""))
        ),
        "instance_spec_matches_freeze": (
            str(scenario.get("instance_spec_sha256", ""))
            == str(freeze.get("instance_spec_semantic_sha256", ""))
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


def _expected_lock_details(
    *,
    scenario_id: str,
    evaluation_id: str,
    provider: str,
    model: str,
    execution_control: bool,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "evaluation_id": evaluation_id,
        "provider": provider,
        "model": model,
        "execution_control": execution_control,
    }


def _load_matching_locked_session(
    *,
    scenario_path: Path,
    freeze_path: Path,
    usage_ledger_path: Path,
    evaluation_id: str,
    provider: str,
    model: str,
    execution_control: bool,
) -> HiddenEvaluationSession:
    scenario = load_json_strict(scenario_path)
    freeze = load_json_strict(freeze_path)
    ledger = load_json_strict(usage_ledger_path)
    failures = list(validate_usage_ledger(ledger))
    scenario_id = str(scenario.get("scenario_id", ""))
    if scenario.get("benchmark_split") != "hidden_test":
        failures.append("split_is_hidden_test")
    if scenario.get("benchmark_tier") != "hard":
        failures.append("tier_is_hard")
    if not bool(
        scenario.get("evaluation_status", {}).get(
            "hidden_test_eligible",
            False,
        )
    ):
        failures.append("scenario_declares_hidden_eligibility")
    if freeze.get("status") != "active":
        failures.append("freeze_is_active")
    if str(freeze.get("scenario_id", "")) != scenario_id:
        failures.append("scenario_ids_match")
    if file_sha256(scenario_path) != str(
        freeze.get("scenario_sha256", "")
    ):
        failures.append("scenario_bytes_match_freeze")
    if str(scenario.get("instance_spec_sha256", "")) != str(
        freeze.get("instance_spec_semantic_sha256", "")
    ):
        failures.append("instance_spec_matches_freeze")
    events = ledger.get("events", [])
    names = [
        str(item.get("event", ""))
        for item in events
        if isinstance(item, dict)
    ]
    if names not in (
        ["frozen", "evaluation_locked"],
        ["generated", "frozen", "evaluation_locked"],
    ):
        failures.append("ledger_ends_at_matching_evaluation_lock")
    lock_event = (
        events[-1]
        if events
        and isinstance(events[-1], dict)
        and events[-1].get("event") == "evaluation_locked"
        else {}
    )
    expected = _expected_lock_details(
        scenario_id=scenario_id,
        evaluation_id=evaluation_id,
        provider=provider,
        model=model,
        execution_control=execution_control,
    )
    details = lock_event.get("details", {})
    if not isinstance(details, dict) or any(
        details.get(key) != value for key, value in expected.items()
    ):
        failures.append("evaluation_lock_details_match")
    commitment = str(freeze.get("public_commitment_sha256", ""))
    if (
        not commitment
        or str(ledger.get("public_commitment_sha256", "")) != commitment
        or str(details.get("public_commitment_sha256", "")) != commitment
    ):
        failures.append("evaluation_lock_commitment_matches")
    lock_hash = str(lock_event.get("event_sha256", ""))
    if not lock_hash:
        failures.append("evaluation_lock_event_hash")
    if failures:
        raise RuntimeError(
            "hidden evaluation session is not valid for provider access: "
            f"{failures}"
        )
    return HiddenEvaluationSession(
        scenario_id=scenario_id,
        evaluation_id=evaluation_id,
        provider=provider,
        model=model,
        execution_control=execution_control,
        usage_ledger_path=usage_ledger_path.resolve(),
        lock_event_sha256=lock_hash,
    )


def begin_hidden_test_evaluation(
    *,
    scenario_path: Path,
    freeze_path: Path,
    usage_ledger_path: Path,
    evaluation_id: str,
    provider: str,
    model: str,
    execution_control: bool,
) -> HiddenEvaluationSession:
    """Atomically lock an unseen instance, or resume the same locked run.

    A resume is accepted only when the immutable scenario identity, model,
    provider, condition, evaluation identifier, commitment and ledger head all
    match.  A different evaluation therefore fails before provider access.
    """

    if not evaluation_id.strip():
        raise ValueError("hidden evaluation id must be non-empty")
    scenario_path = scenario_path.resolve()
    freeze_path = freeze_path.resolve()
    usage_ledger_path = usage_ledger_path.resolve()
    try:
        eligibility = verify_hidden_test_eligibility(
            scenario_path=scenario_path,
            freeze_path=freeze_path,
            usage_ledger_path=usage_ledger_path,
        )
    except RuntimeError:
        return _load_matching_locked_session(
            scenario_path=scenario_path,
            freeze_path=freeze_path,
            usage_ledger_path=usage_ledger_path,
            evaluation_id=evaluation_id,
            provider=provider,
            model=model,
            execution_control=execution_control,
        )
    scenario_id = str(eligibility["observed"]["scenario_id"])
    details = _expected_lock_details(
        scenario_id=scenario_id,
        evaluation_id=evaluation_id,
        provider=provider,
        model=model,
        execution_control=execution_control,
    )
    try:
        append_usage_event(
            ledger_path=usage_ledger_path,
            event="evaluation_locked",
            details=details,
        )
    except (RuntimeError, ValueError):
        # Another process may have won the atomic append. Only the identical
        # evaluation session is allowed to continue.
        return _load_matching_locked_session(
            scenario_path=scenario_path,
            freeze_path=freeze_path,
            usage_ledger_path=usage_ledger_path,
            evaluation_id=evaluation_id,
            provider=provider,
            model=model,
            execution_control=execution_control,
        )
    return _load_matching_locked_session(
        scenario_path=scenario_path,
        freeze_path=freeze_path,
        usage_ledger_path=usage_ledger_path,
        evaluation_id=evaluation_id,
        provider=provider,
        model=model,
        execution_control=execution_control,
    )


def validate_hidden_evaluation_session(
    *,
    scenario_path: Path,
    freeze_path: Path,
    session: HiddenEvaluationSession,
) -> None:
    observed = _load_matching_locked_session(
        scenario_path=scenario_path.resolve(),
        freeze_path=freeze_path.resolve(),
        usage_ledger_path=session.usage_ledger_path,
        evaluation_id=session.evaluation_id,
        provider=session.provider,
        model=session.model,
        execution_control=session.execution_control,
    )
    if observed != session:
        raise RuntimeError("hidden evaluation session proof changed")


def consume_hidden_test_evaluation(
    *,
    scenario_path: Path,
    freeze_path: Path,
    session: HiddenEvaluationSession,
) -> dict[str, Any]:
    """Close a completed hidden evaluation session."""

    validate_hidden_evaluation_session(
        scenario_path=scenario_path,
        freeze_path=freeze_path,
        session=session,
    )
    return append_usage_event(
        ledger_path=session.usage_ledger_path,
        event="consumed",
        details={
            "scenario_id": session.scenario_id,
            "evaluation_id": session.evaluation_id,
            "provider": session.provider,
            "model": session.model,
            "execution_control": session.execution_control,
        },
    )


__all__ = [
    "HiddenEvaluationSession",
    "begin_hidden_test_evaluation",
    "consume_hidden_test_evaluation",
    "validate_hidden_evaluation_session",
    "verify_hidden_test_eligibility",
]
