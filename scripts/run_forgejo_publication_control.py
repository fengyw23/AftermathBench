from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_publication_recovery import (
    ForgejoPublicationEnvironment,
    evaluate_forgejo_publication_recovery,
    reference_forgejo_publication_recovery,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the state-driven Forgejo publication reference."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    environment = ForgejoPublicationEnvironment(
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
    error = None
    try:
        trace = reference_forgejo_publication_recovery(environment)
    except Exception as caught:  # noqa: BLE001 - retain terminal evidence
        trace = environment.event_log()
        error = {
            "exception_type": type(caught).__name__,
            "error": str(caught),
        }
    evidence = environment.snapshot()
    evaluation = evaluate_forgejo_publication_recovery(
        evidence, prefix=prefix
    )
    mutation_tools = [
        step["tool"]
        for step in trace
        if step["tool"] in environment.MUTATION_TOOLS
    ]
    query_tools = [
        step["tool"]
        for step in trace
        if step["tool"] not in environment.MUTATION_TOOLS
    ]
    repaired_groups = {
        "release": evaluation.checks["target_release_published_once"],
        "assets": evaluation.checks[
            "exact_approved_asset_set_published"
        ],
        "coordinator": evaluation.checks[
            "coordinator_effect_applied_once"
        ],
        "provenance": evaluation.checks[
            "provenance_effect_applied_once"
        ],
    }
    report = {
        "schema_version": "0.2",
        "scenario_id": prefix["scenario_id"],
        "instance_spec_sha256": prefix["instance_spec_sha256"],
        "variant": args.variant,
        "control": "state_driven_reference_using_agent_visible_tools",
        "reference_trace": list(trace),
        "query_tools": query_tools,
        "mutation_tools": mutation_tools,
        "repaired_groups": repaired_groups,
        "downstream_repairs": sum(repaired_groups.values()),
        "control_error": error,
        "final_evidence": evidence,
        "evaluation": {
            "passed": evaluation.passed,
            "components": evaluation.components,
            "checks": evaluation.checks,
            "diagnostics": evaluation.diagnostics,
            "failures": evaluation.failures,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "passed": evaluation.passed,
                "mutations": mutation_tools,
                "failures": evaluation.failures,
                "control_error": error,
            },
            indent=2,
        )
    )
    return 0 if evaluation.passed and error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
