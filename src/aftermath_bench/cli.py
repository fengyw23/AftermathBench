from __future__ import annotations

import argparse
import json

from .admission import validate_task
from .evaluator import evaluate
from .scenarios.enterprise_transfer import (
    VARIANTS,
    EnterpriseTransferEnv,
    reference_recovery,
)
from .schema import load_task


def _validate() -> int:
    report = validate_task(load_task())
    print(json.dumps(
        {
            "task_id": report.task_id,
            "passed": report.passed,
            "observed": report.observed,
            "failures": report.failures,
        },
        indent=2,
    ))
    return 0 if report.passed else 1


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aftermath-bench")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="run hard-task admission checks")
    demo = subparsers.add_parser("demo", help="run reference recovery")
    demo.add_argument("--variant", choices=VARIANTS)
    demo.add_argument("--all", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "validate":
        return _validate()
    variants = VARIANTS if args.all else (args.variant or VARIANTS[0],)
    return _run_demo(variants)

