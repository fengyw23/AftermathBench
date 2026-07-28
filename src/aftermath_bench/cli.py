from __future__ import annotations

import argparse
import json

from .admission import validate_task
from .baselines import run_release_baselines
from .evaluator import evaluate
from .scenarios.enterprise_transfer import (
    VARIANTS,
    EnterpriseTransferEnv,
    reference_recovery,
)
from .scenarios.release_migration import (
    RELEASE_VARIANTS,
    build_release_failure_state,
    evaluate_release,
    reference_release_recovery,
)
from .schema import load_task, task_paths


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


def _run_demo(variants: tuple[str, ...]) -> int:
    all_passed = True
    for variant in variants:
        env = EnterpriseTransferEnv(variant)
        reference_recovery(env)
        result = evaluate(env.snapshot())
        all_passed = all_passed and result.passed
        print(json.dumps(
            {
                "variant": variant,
                "passed": result.passed,
                "queries": env.state["queries"],
                "mutations": env.state["mutations"],
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
                        event.tool for event in environment.events[6:]
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
    demo = subparsers.add_parser("demo", help="run reference recovery")
    demo.add_argument("--variant", choices=VARIANTS)
    demo.add_argument("--all", action="store_true")
    release_demo = subparsers.add_parser(
        "demo-release",
        help="run the Git/database/registry/deployment recovery",
    )
    release_demo.add_argument("--variant", choices=RELEASE_VARIANTS)
    release_demo.add_argument("--all", action="store_true")
    subparsers.add_parser(
        "baselines",
        help="run fixed recovery heuristics on matched release faults",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "validate":
        return _validate()
    if args.command == "baselines":
        print(json.dumps(run_release_baselines(), indent=2))
        return 0
    if args.command == "demo-release":
        variants = RELEASE_VARIANTS if args.all else (
            args.variant or RELEASE_VARIANTS[0],
        )
        return _run_release_demo(variants)
    variants = VARIANTS if args.all else (args.variant or VARIANTS[0],)
    return _run_demo(variants)
