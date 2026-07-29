from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_recovery import (
    ForgejoReleaseEnvironment,
    evaluate_forgejo_release_recovery,
)
from aftermath_bench.integrations.forgejo_release_baselines import (
    BASELINE_NAMES,
    run_fixed_forgejo_baseline,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute one fixed policy at a native Forgejo boundary."
    )
    parser.add_argument("--baseline", choices=BASELINE_NAMES, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _read(args.credentials)
    prefix = _read(args.prefix)
    environment = ForgejoReleaseEnvironment(
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
    trace = run_fixed_forgejo_baseline(
        args.baseline,
        environment=environment,
    )
    evaluation = evaluate_forgejo_release_recovery(
        environment.snapshot(), prefix=prefix
    )
    report = {
        "schema_version": "0.1",
        "scenario_id": "forgejo-pr-release-dev-001",
        "variant": args.variant,
        "baseline": args.baseline,
        "source": "executed against the native failure state",
        "trace": list(trace),
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
                "baseline": args.baseline,
                "passed": evaluation.passed,
                "failures": evaluation.failures,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
