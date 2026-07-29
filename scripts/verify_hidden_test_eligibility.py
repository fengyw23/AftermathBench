from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def verify_hidden_test_eligibility(
    *,
    scenario_path: Path,
    freeze_path: Path,
) -> dict[str, Any]:
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
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
    }
    checks = {
        "scenario_ids_match": (
            observed["scenario_id"] == str(freeze.get("scenario_id", ""))
        ),
        "split_is_hidden_test": observed["benchmark_split"] == "hidden_test",
        "tier_is_hard": observed["benchmark_tier"] == "hard",
        "scenario_declares_hidden_eligibility": observed["hidden_test_eligible"],
        "freeze_is_active": observed["freeze_status"] == "active",
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
    args = parser.parse_args()
    result = verify_hidden_test_eligibility(
        scenario_path=args.scenario,
        freeze_path=args.freeze,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
