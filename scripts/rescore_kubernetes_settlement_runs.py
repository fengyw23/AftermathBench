from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.kubernetes_settlement_recovery import (
    evaluate_kubernetes_settlement_recovery,
)


def rescore(run_directory: Path) -> dict[str, Any]:
    reports = []
    for path in sorted(run_directory.glob("repetition-*/*.json")):
        if path.name.endswith("-failure.json"):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if "final_evidence" not in raw:
            continue
        evaluation = evaluate_kubernetes_settlement_recovery(
            raw["final_evidence"]
        )
        reports.append(
            {
                "scenario_id": raw.get("scenario_id"),
                "variant": raw.get("variant"),
                "path": str(path),
                "original_passed": bool(
                    raw.get("evaluation", {}).get("passed")
                ),
                "rescored_passed": evaluation.passed,
                "original_failures": raw.get("evaluation", {}).get(
                    "failures", []
                ),
                "rescored_failures": list(evaluation.failures),
            }
        )
    passed = sum(item["rescored_passed"] for item in reports)
    return {
        "schema_version": "0.1",
        "evaluator_revision": (
            "receipt status aligned with model-visible Job receipt status=approved"
        ),
        "completed_runs": len(reports),
        "rescored_task_pass_rate": passed / len(reports) if reports else 0.0,
        "changed_outcome_count": sum(
            item["original_passed"] != item["rescored_passed"]
            for item in reports
        ),
        "reports": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = rescore(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["completed_runs"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
