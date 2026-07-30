from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from aftermath_bench.integrations.kubernetes_interaction_recovery import (
    evaluate_kubernetes_interaction_recovery,
)


def rescore_reports(
    root: Path,
    *,
    evaluator: Callable[[dict[str, Any]], Any] = (
        evaluate_kubernetes_interaction_recovery
    ),
) -> dict[str, Any]:
    rows = []
    load_errors = []
    for path in sorted(root.rglob("*.json")):
        if path.name.endswith("-failure.json") or path.name in {
            "summary.json",
            "analysis.json",
            "rescore.json",
        }:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            load_errors.append(f"{path}: {error}")
            continue
        if report.get("family") != "k8s-constraint-interaction-recovery":
            continue
        if "final_evidence" not in report or "evaluation" not in report:
            continue
        rescored = evaluator(report["final_evidence"])
        original_passed = bool(report["evaluation"].get("passed"))
        rows.append(
            {
                "variant": str(report.get("variant")),
                "original_passed": original_passed,
                "rescored_passed": bool(rescored.passed),
                "changed": original_passed != bool(rescored.passed),
                "original_failures": list(
                    report["evaluation"].get("failures", ())
                ),
                "rescored_failures": list(rescored.failures),
                "path": path.relative_to(root).as_posix(),
            }
        )
    total = len(rows)
    return {
        "schema_version": "0.1",
        "evaluator_revision": "contract-scalars-normalized",
        "completed_runs": total,
        "load_errors": load_errors,
        "original_task_pass_rate": (
            sum(row["original_passed"] for row in rows) / total
            if total
            else 0.0
        ),
        "rescored_task_pass_rate": (
            sum(row["rescored_passed"] for row in rows) / total
            if total
            else 0.0
        ),
        "changed_run_count": sum(row["changed"] for row in rows),
        "reports": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rescore archived Kubernetes interaction trajectories."
    )
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = rescore_reports(args.run_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["load_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
