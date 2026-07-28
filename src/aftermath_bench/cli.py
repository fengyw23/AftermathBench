from __future__ import annotations

import argparse
import json

from .admission import validate_task
from .baselines import run_itsm_baselines, run_release_baselines
from .erpnext_model_runner import run_live_erpnext_agent
from .evaluator import evaluate
from .integrations.enterprise_ops_assets import fetch_enterpriseops_archive
from .model_runner import (
    client_from_environment,
    run_itsm_agent,
    run_itsm_suite,
)
from .native_admission import validate_native_scenario
from .native_model_runner import run_live_native_agent
from .native_scenario import load_native_scenario, native_scenario_paths
from .scenarios.enterprise_transfer import (
    VARIANTS,
    build_enterprise_failure_state,
    reference_recovery,
)
from .scenarios.release_migration import (
    RELEASE_VARIANTS,
    build_release_failure_state,
    evaluate_release,
    reference_release_recovery,
)
from .scenarios.itsm_major_incident import (
    ITSM_VARIANTS,
    build_itsm_failure_state,
    evaluate_itsm,
    reference_itsm_recovery,
)
from .schema import load_task, task_paths
from .runtime_gate import (
    load_runtime_manifest,
    runtime_manifest_paths,
    validate_runtime_manifest,
)


def _validate() -> int:
    all_passed = True
    for path in task_paths():
        report = validate_task(load_task(path))
        all_passed = all_passed and report.passed
        print(json.dumps(
            {
                "task_id": report.task_id,
                "passed": report.passed,
                "observed": report.observed,
                "failures": report.failures,
            },
            indent=2,
        ))
    return 0 if all_passed else 1


def _validate_runtimes() -> int:
    reports = [
        validate_runtime_manifest(load_runtime_manifest(path))
        for path in runtime_manifest_paths()
    ]
    for report in reports:
        print(json.dumps(
            {
                "runtime_id": report.runtime_id,
                "source_audit_passed": report.source_audit_passed,
                "execution_admitted": report.execution_admitted,
                "source_checks": report.source_checks,
                "execution_checks": report.execution_checks,
                "failures": report.failures,
            },
            indent=2,
        ))
    truthful = all(
        "source_status_truthful" not in report.failures
        and "execution_status_truthful" not in report.failures
        for report in reports
    )
    return 0 if truthful else 1


def _validate_native_scenarios(path: str | None = None) -> int:
    paths = (path,) if path is not None else native_scenario_paths()
    all_truthful = True
    for scenario_path in paths:
        report = validate_native_scenario(
            load_native_scenario(scenario_path)
        )
        all_truthful = all_truthful and report.passed
        print(json.dumps(
            {
                "scenario_id": report.scenario_id,
                "requested_tier": report.requested_tier,
                "admitted_tier": report.admitted_tier,
                "passed": report.passed,
                "observed": report.observed,
                "failures": report.failures,
                "artifact_sha256": report.artifact_sha256,
            },
            indent=2,
        ))
    return 0 if all_truthful else 1


def _run_demo(variants: tuple[str, ...]) -> int:
    all_passed = True
    for variant in variants:
        env, _proxy, failure = build_enterprise_failure_state(variant)
        reference_recovery(env)
        result = evaluate(env.snapshot())
        all_passed = all_passed and result.passed
        recovery_events = env.events_after("failure")
        print(json.dumps(
            {
                "variant": variant,
                "surface_failure": failure,
                "passed": result.passed,
                "recovery_tools": [event.tool for event in recovery_events],
                "failures": result.failures,
            },
            indent=2,
        ))
    return 0 if all_passed else 1


def _run_release_demo(variants: tuple[str, ...]) -> int:
    all_passed = True
    for variant in variants:
        environment, _proxy, failure = build_release_failure_state(variant)
        try:
            reference_release_recovery(environment)
            result = evaluate_release(environment.snapshot())
            all_passed = all_passed and result["passed"]
            print(json.dumps(
                {
                    "variant": variant,
                    "surface_failure": failure,
                    "passed": result["passed"],
                    "components": result,
                    "recovery_tools": [
                        event.tool
                        for event in environment.events_after("failure")
                    ],
                },
                indent=2,
            ))
        finally:
            environment.close()
    return 0 if all_passed else 1


def _run_itsm_demo(
    variants: tuple[str, ...],
    *,
    seed_archive: str | None = None,
) -> int:
    all_passed = True
    for variant in variants:
        environment, _proxy, failure = build_itsm_failure_state(
            variant,
            seed_archive=seed_archive,
        )
        try:
            reference_itsm_recovery(environment)
            result = evaluate_itsm(environment)
            all_passed = all_passed and result["passed"]
            print(json.dumps(
                {
                    "variant": variant,
                    "surface_failure": failure,
                    "passed": result["passed"],
                    "components": result,
                    "recovery_tools": [
                        event.tool
                        for event in environment.events_after("failure")
                    ],
                },
                indent=2,
            ))
        finally:
            environment.close()
    return 0 if all_passed else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aftermath-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="run hard-task admission checks")
    subparsers.add_parser(
        "validate-runtimes",
        help="audit open-source and execution admission for every runtime",
    )
    native_validation = subparsers.add_parser(
        "validate-native-scenario",
        help="validate replay-derived native scenario difficulty",
    )
    native_validation.add_argument("--scenario")
    native_validation.add_argument(
        "--execute",
        action="store_true",
        help="reserved for live replay validation; artifacts are always audited",
    )
    demo = subparsers.add_parser("demo", help="run reference recovery")
    demo.add_argument("--variant", choices=VARIANTS)
    demo.add_argument("--all", action="store_true")
    release_demo = subparsers.add_parser(
        "demo-release",
        help="run the Git/database/registry/deployment recovery",
    )
    release_demo.add_argument("--variant", choices=RELEASE_VARIANTS)
    release_demo.add_argument("--all", action="store_true")
    itsm_demo = subparsers.add_parser(
        "demo-itsm",
        help="run the multi-table ITSM major-incident recovery",
    )
    itsm_demo.add_argument("--variant", choices=ITSM_VARIANTS)
    itsm_demo.add_argument("--all", action="store_true")
    itsm_demo.add_argument(
        "--enterpriseops-archive",
        help="use the pinned full EnterpriseOps gym_dbs.zip seed",
    )
    fetch_assets = subparsers.add_parser(
        "fetch-enterpriseops",
        help="download and verify the pinned EnterpriseOps seed archive",
    )
    fetch_assets.add_argument("--destination")
    model_run = subparsers.add_parser(
        "run-itsm-model",
        help="run a model against one hidden ITSM commit-state variant",
    )
    model_run.add_argument(
        "--provider",
        required=True,
        choices=("openai-compatible", "anthropic"),
    )
    model_run.add_argument("--model", required=True)
    model_run.add_argument("--base-url")
    model_run.add_argument("--api-key-env", default="AFTERMATH_API_KEY")
    model_run.add_argument("--variant", required=True, choices=ITSM_VARIANTS)
    seed_source = model_run.add_mutually_exclusive_group()
    seed_source.add_argument("--enterpriseops-archive")
    seed_source.add_argument(
        "--minimal-fixture",
        action="store_true",
        help="use only the small test fixture instead of the official full seed",
    )
    model_run.add_argument("--max-turns", type=int, default=15)
    model_run.add_argument("--output")
    model_suite = subparsers.add_parser(
        "run-itsm-suite",
        help="run every hidden ITSM state repeatedly and aggregate results",
    )
    model_suite.add_argument(
        "--provider",
        required=True,
        choices=("openai-compatible", "anthropic"),
    )
    model_suite.add_argument("--model", required=True)
    model_suite.add_argument("--base-url")
    model_suite.add_argument("--api-key-env", default="AFTERMATH_API_KEY")
    model_suite.add_argument("--enterpriseops-archive")
    model_suite.add_argument("--repetitions", type=int, default=5)
    model_suite.add_argument("--max-turns", type=int, default=15)
    model_suite.add_argument("--output-directory", required=True)
    erpnext_model_run = subparsers.add_parser(
        "run-erpnext-model",
        help="run a model against one live native ERPNext failure state",
    )
    erpnext_model_run.add_argument(
        "--provider",
        required=True,
        choices=("openai-compatible", "anthropic"),
    )
    native_model_run = subparsers.add_parser(
        "run-native-model",
        help="run a model on a manifest-driven native recovery scenario",
    )
    native_model_run.add_argument(
        "--provider",
        required=True,
        choices=("openai-compatible", "anthropic"),
    )
    native_model_run.add_argument("--model", required=True)
    native_model_run.add_argument("--base-url")
    native_model_run.add_argument(
        "--api-key-env",
        default="AFTERMATH_API_KEY",
    )
    native_model_run.add_argument("--scenario", required=True)
    native_model_run.add_argument("--credentials", required=True)
    native_model_run.add_argument("--prefix", required=True)
    native_model_run.add_argument("--failure-report", required=True)
    native_model_run.add_argument("--max-turns", type=int, default=15)
    native_model_run.add_argument(
        "--execution-control",
        action="store_true",
        help="supply the correct recovery scope to isolate tool execution",
    )
    native_model_run.add_argument("--output", required=True)
    native_model_run.add_argument(
        "--erpnext-base-url",
        default="http://127.0.0.1:8080",
    )
    native_model_run.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    erpnext_model_run.add_argument("--model", required=True)
    erpnext_model_run.add_argument("--base-url")
    erpnext_model_run.add_argument(
        "--api-key-env",
        default="AFTERMATH_API_KEY",
    )
    erpnext_model_run.add_argument(
        "--variant",
        required=True,
        choices=(
            "request_not_reached",
            "database_committed_response_lost",
            "after_commit_enqueue_failed",
            "async_job_pending",
        ),
    )
    erpnext_model_run.add_argument("--credentials", required=True)
    erpnext_model_run.add_argument("--prefix", required=True)
    erpnext_model_run.add_argument("--failure-report", required=True)
    erpnext_model_run.add_argument("--max-turns", type=int, default=15)
    erpnext_model_run.add_argument("--output", required=True)
    erpnext_model_run.add_argument(
        "--erpnext-base-url",
        default="http://127.0.0.1:8080",
    )
    erpnext_model_run.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    subparsers.add_parser(
        "baselines",
        help="run fixed recovery heuristics on matched release faults",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "validate":
        return _validate()
    if args.command == "validate-runtimes":
        return _validate_runtimes()
    if args.command == "validate-native-scenario":
        return _validate_native_scenarios(args.scenario)
    if args.command == "baselines":
        print(json.dumps(
            {
                "release_migration": run_release_baselines(),
                "itsm_major_incident": run_itsm_baselines(),
            },
            indent=2,
        ))
        return 0
    if args.command == "fetch-enterpriseops":
        print(fetch_enterpriseops_archive(args.destination))
        return 0
    if args.command == "run-itsm-model":
        seed_archive = None
        if not args.minimal_fixture:
            seed_archive = (
                args.enterpriseops_archive
                or str(fetch_enterpriseops_archive())
            )
        client = client_from_environment(
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
        )
        report = run_itsm_agent(
            client,
            variant=args.variant,
            seed_archive=seed_archive,
            max_turns=args.max_turns,
            output_path=args.output,
        )
        print(json.dumps(
            {
                "run_id": report["run_id"],
                "evaluation": report["evaluation"],
                "stop_reason": report["stop_reason"],
                "output": args.output,
            },
            indent=2,
        ))
        return 0 if report["evaluation"]["passed"] else 1
    if args.command == "run-itsm-suite":
        archive = (
            args.enterpriseops_archive
            or str(fetch_enterpriseops_archive())
        )
        client = client_from_environment(
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
        )
        summary = run_itsm_suite(
            client,
            seed_archive=archive,
            output_directory=args.output_directory,
            repetitions=args.repetitions,
            max_turns=args.max_turns,
        )
        print(json.dumps(
            {
                "model": summary["model"],
                "completed_runs": summary["completed_runs"],
                "run_errors": summary["run_errors"],
                "task_pass_rate": summary["task_pass_rate"],
                "matched_group_success_rate": summary[
                    "matched_group_success_rate"
                ],
            },
            indent=2,
        ))
        return 0 if not summary["run_errors"] else 2
    if args.command == "run-erpnext-model":
        client = client_from_environment(
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
        )
        report = run_live_erpnext_agent(
            client,
            variant=args.variant,
            credentials_path=args.credentials,
            prefix_path=args.prefix,
            failure_report_path=args.failure_report,
            max_turns=args.max_turns,
            execution_control=False,
            output_path=args.output,
            erpnext_base_url=args.erpnext_base_url,
            container_cli=args.container_cli,
        )
        print(json.dumps(
            {
                "run_id": report["run_id"],
                "evaluation": report["evaluation"],
                "trajectory_diagnostics": report[
                    "trajectory_diagnostics"
                ],
                "stop_reason": report["stop_reason"],
                "output": args.output,
            },
            indent=2,
        ))
        return 0 if report["evaluation"]["passed"] else 1
    if args.command == "run-native-model":
        client = client_from_environment(
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            api_key_env=args.api_key_env,
        )
        report = run_live_native_agent(
            client,
            scenario_path=args.scenario,
            credentials_path=args.credentials,
            prefix_path=args.prefix,
            failure_report_path=args.failure_report,
            max_turns=args.max_turns,
            execution_control=args.execution_control,
            output_path=args.output,
            erpnext_base_url=args.erpnext_base_url,
            container_cli=args.container_cli,
        )
        print(json.dumps(
            {
                "run_id": report["run_id"],
                "evaluation": report["evaluation"],
                "trajectory_diagnostics": report[
                    "trajectory_diagnostics"
                ],
                "stop_reason": report["stop_reason"],
                "output": args.output,
            },
            indent=2,
        ))
        return 0 if report["evaluation"]["passed"] else 1
    if args.command == "demo-itsm":
        variants = ITSM_VARIANTS if args.all else (
            args.variant or ITSM_VARIANTS[0],
        )
        return _run_itsm_demo(
            variants,
            seed_archive=args.enterpriseops_archive,
        )
    if args.command == "demo-release":
        variants = RELEASE_VARIANTS if args.all else (
            args.variant or RELEASE_VARIANTS[0],
        )
        return _run_release_demo(variants)
    variants = VARIANTS if args.all else (args.variant or VARIANTS[0],)
    return _run_demo(variants)
