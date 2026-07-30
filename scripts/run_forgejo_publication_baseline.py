from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_publication_baselines import (
    PUBLICATION_BASELINE_NAMES,
    run_fixed_forgejo_publication_baseline,
)
from aftermath_bench.integrations.forgejo_publication_recovery import (
    ForgejoPublicationEnvironment,
    evaluate_forgejo_publication_recovery,
)
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute a fixed policy at a publication boundary."
    )
    parser.add_argument(
        "--baseline",
        choices=PUBLICATION_BASELINE_NAMES,
        required=True,
    )
    parser.add_argument("--variant", required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
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
    trace = run_fixed_forgejo_publication_baseline(
        args.baseline,
        environment=environment,
    )
    evaluation = evaluate_forgejo_publication_recovery(
        environment.snapshot(), prefix=prefix
    )
    report = {
        "schema_version": "0.2",
        "scenario_id": "forgejo-release-publication-dev-002",
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
