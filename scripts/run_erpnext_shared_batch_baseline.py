from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import default_worker_control
from aftermath_bench.integrations.erpnext_shared_batch_agent import (
    ERPNextSharedBatchEnvironment,
)
from aftermath_bench.integrations.erpnext_shared_batch_baselines import (
    SHARED_BATCH_BASELINE_NAMES,
    run_fixed_shared_batch_baseline,
)
from aftermath_bench.integrations.erpnext_shared_batch_evaluator import (
    evaluate_shared_batch_terminal,
)
from aftermath_bench.integrations.erpnext_shared_batch_evidence import (
    ERPNextSharedBatchEvidenceCollector,
)
from aftermath_bench.integrations.erpnext_shared_batch_projection import (
    project_shared_batch_terminal,
)
from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute one fixed native shared-batch recovery baseline."
    )
    parser.add_argument(
        "--baseline", choices=SHARED_BATCH_BASELINE_NAMES, required=True
    )
    parser.add_argument("--variant", required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument(
        "--container-cli", choices=("docker", "podman"), default="docker"
    )
    args = parser.parse_args()

    root = repository_root()
    prefix = json.loads(args.prefix.read_text(encoding="utf-8"))
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    stack = ERPNextStack(
        compose_file=root / "runtimes" / "erpnext" / "compose.yaml",
        container_cli=args.container_cli,
        db_root_password=os.environ.get("AFTERMATH_DB_ROOT_PASSWORD", "aftermath-root"),
    )
    environment = ERPNextSharedBatchEnvironment(
        adapter=adapter,
        prefix=prefix,
        stack=stack,
        worker_control=default_worker_control(root, container_cli=args.container_cli),
        collector=ERPNextSharedBatchEvidenceCollector(adapter),
    )
    trace = run_fixed_shared_batch_baseline(
        args.baseline, environment=environment, prefix=prefix
    )
    raw_evidence = environment.snapshot()
    projected = project_shared_batch_terminal(
        raw_evidence,
        prefix=prefix,
        fixture=prefix["evaluation_fixture"],
    )
    evaluation = evaluate_shared_batch_terminal(
        projected,
        fixture=prefix["evaluation_fixture"],
        protected_fingerprints=prefix["protected_fingerprints"],
    )
    report = {
        "schema_version": "0.1",
        "artifact_type": "erpnext_shared_batch_fixed_baseline",
        "scenario_id": prefix["scenario_id"],
        "variant": args.variant,
        "baseline": args.baseline,
        "source": "executed against the native shared-batch failure state",
        "trace": trace,
        "final_evidence": raw_evidence,
        "projected_evidence": projected,
        "evaluation": evaluation,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario_id": prefix["scenario_id"],
                "variant": args.variant,
                "baseline": args.baseline,
                "passed": evaluation["passed"],
                "failures": evaluation["failures"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
