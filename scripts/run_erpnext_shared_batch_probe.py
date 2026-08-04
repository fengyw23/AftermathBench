from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.erpnext_faults import default_worker_control
from aftermath_bench.integrations.erpnext_shared_batch_agent import (
    ERPNextSharedBatchEnvironment,
)
from aftermath_bench.integrations.erpnext_shared_batch_evaluator import (
    evaluate_shared_batch_terminal,
)
from aftermath_bench.integrations.erpnext_shared_batch_evidence import (
    ERPNextSharedBatchEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_shared_batch_probes import (
    SHARED_BATCH_INTERACTION_PROBES,
    run_shared_batch_interaction_probe,
)
from aftermath_bench.integrations.erpnext_shared_batch_projection import (
    project_shared_batch_terminal,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.schema import repository_root


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _evaluate(raw: dict[str, Any], prefix: dict[str, Any]) -> dict[str, Any]:
    projected = project_shared_batch_terminal(
        raw, prefix=prefix, fixture=prefix["evaluation_fixture"]
    )
    return evaluate_shared_batch_terminal(
        projected,
        fixture=prefix["evaluation_fixture"],
        protected_fingerprints=prefix["protected_fingerprints"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay a native repair/preservation conflict probe."
    )
    parser.add_argument("--variant", required=True)
    parser.add_argument(
        "--probe", choices=SHARED_BATCH_INTERACTION_PROBES, required=True
    )
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--failure-report", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--container-cli", choices=("docker", "podman"), default="docker"
    )
    args = parser.parse_args()

    root = repository_root()
    prefix = json.loads(args.prefix.read_text(encoding="utf-8"))
    failure = json.loads(args.failure_report.read_text(encoding="utf-8"))
    if str(failure.get("variant")) != args.variant:
        raise ValueError("failure report variant does not match --variant")
    boundary_raw = failure["boundary_evidence"]
    boundary_evaluation = _evaluate(boundary_raw, prefix)
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    collector = ERPNextSharedBatchEvidenceCollector(adapter)
    environment = ERPNextSharedBatchEnvironment(
        adapter=adapter,
        prefix=prefix,
        stack=ERPNextStack(
            compose_file=root / "runtimes" / "erpnext" / "compose.yaml",
            container_cli=args.container_cli,
            db_root_password=os.environ.get(
                "AFTERMATH_DB_ROOT_PASSWORD", "aftermath-root"
            ),
        ),
        worker_control=default_worker_control(root, container_cli=args.container_cli),
        collector=collector,
    )
    trace = run_shared_batch_interaction_probe(
        environment, prefix=prefix, probe=args.probe
    )
    final_raw = environment.snapshot()
    final_evaluation = _evaluate(final_raw, prefix)
    repaired = sorted(
        key
        for key, value in final_evaluation["checks"].items()
        if value and not boundary_evaluation["checks"][key]
    )
    broken = sorted(
        key
        for key, value in final_evaluation["checks"].items()
        if not value and boundary_evaluation["checks"][key]
    )
    report = {
        "schema_version": "1.0",
        "artifact_type": "erpnext_shared_batch_obligation_probe",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "action_id": args.probe,
        "source": "public-tool replay from the native failure boundary",
        "tool_events": list(trace),
        "source_boundary_sha256": hashlib.sha256(
            args.failure_report.read_bytes()
        ).hexdigest(),
        "result_state_sha256": _canonical_sha256(final_raw),
        "boundary_evaluation": boundary_evaluation,
        "result_evaluation": final_evaluation,
        "derived_repaired_checks": repaired,
        "derived_broken_checks": broken,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    expected_broken = {
        "repair_then_cancel_customer_reservation": {"customer_reservation_preserved"},
        "repair_then_cancel_accepted_quality_inspection": {
            "protected_native_documents_unchanged"
        },
        "repair_then_cancel_unrelated_receipt": {
            "protected_native_documents_unchanged"
        },
    }[args.probe]
    expected_conflict = bool(repaired) and bool(expected_broken & set(broken))
    print(
        json.dumps(
            {
                "variant": args.variant,
                "action_id": args.probe,
                "repaired_checks": repaired,
                "broken_checks": broken,
                "expected_conflict": expected_conflict,
            },
            indent=2,
        )
    )
    return 0 if expected_conflict else 1


if __name__ == "__main__":
    raise SystemExit(main())
