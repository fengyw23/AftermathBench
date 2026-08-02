from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_package_provenance_recovery import (
    ForgejoPackageProvenanceEnvironment,
    evaluate_forgejo_package_provenance_recovery,
    reference_forgejo_package_provenance_recovery,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--boundary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    boundary = _read(args.boundary)
    environment = ForgejoPackageProvenanceEnvironment(
        api=ForgejoAPI(
            base_url=credentials["base_url"],
            token=credentials["token"],
        ),
        web=ForgejoWebSession(
            base_url=credentials["web_base_url"],
            username=credentials["username"],
            password=credentials["password"],
        ),
        prefix=prefix,
    )
    trace = reference_forgejo_package_provenance_recovery(environment)
    final_state = environment.snapshot()
    evaluation = evaluate_forgejo_package_provenance_recovery(
        final_state,
        prefix=prefix,
    )
    mutation_tools = [
        event["tool"]
        for event in trace
        if event["tool"] in environment.MUTATION_TOOLS
    ]
    query_tools = [
        event["tool"]
        for event in trace
        if event["tool"] not in environment.MUTATION_TOOLS
    ]
    repaired_groups = {
        "package_files": evaluation.checks["exact_provenance_file_set"],
        "index_release": evaluation.checks["one_package_index_release"],
        "external_consumers": evaluation.checks[
            "both_index_consumers_applied"
        ],
        "tracking_closure": evaluation.checks["tracking_issues_closed"],
    }
    payload = {
        "schema_version": "1.0",
        "scenario_id": prefix["scenario_id"],
        "variant": boundary["variant"],
        "reference_trace": trace,
        "mutation_tools": mutation_tools,
        "query_tools": query_tools,
        "repaired_groups": repaired_groups,
        "downstream_repairs": sum(repaired_groups.values()),
        "semantic_recovery_direction": {
            "package_request_not_reached": "publish_missing_version",
            "package_binary_committed_response_lost": (
                "preserve_blob_and_attach_metadata"
            ),
            "package_complete_index_missing": "resume_indexing",
            "package_complete_index_accepted_response_lost": (
                "verify_complete_package"
            ),
        }[boundary["variant"]],
        "final_evidence": final_state,
        "evaluation": {
            "passed": evaluation.passed,
            "components": evaluation.components,
            "checks": evaluation.checks,
            "failures": list(evaluation.failures),
            "diagnostics": evaluation.diagnostics,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "variant": boundary["variant"],
                "passed": evaluation.passed,
                "tool_calls": len(trace),
            }
        )
    )
    return 0 if evaluation.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
