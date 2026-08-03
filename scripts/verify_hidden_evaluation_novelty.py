from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject a hidden scenario identity retired by a prior evaluation."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--registry-root", type=Path, required=True)
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    scenario_id = str(scenario.get("scenario_id", ""))
    retired = set()
    for path in sorted(args.registry_root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("record_type") == "hidden_evaluation_invalidation"
            and payload.get("disposition", {}).get("hidden_instance_reusable") is False
        ):
            retired.add(str(payload.get("scenario_id", "")))
    passed = bool(scenario_id) and scenario_id not in retired
    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "passed": passed,
                "scenario_id": scenario_id,
                "retired_identity_count": len(retired),
            }
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
