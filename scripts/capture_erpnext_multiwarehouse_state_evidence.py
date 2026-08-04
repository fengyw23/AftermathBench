from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.erpnext_multiwarehouse_state_evidence import (
    build_multiwarehouse_state_evidence,
)
from aftermath_bench.integrations.erpnext_multiwarehouse_evidence import (
    ERPNextMultiwarehouseEvidenceCollector,
)
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.strict_json import load_json_strict


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a hash-bound ERPNext multiwarehouse reset or boundary."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--phase", choices=("reset", "boundary"), required=True)
    parser.add_argument("--bundle-manifest", type=Path, required=True)
    parser.add_argument("--failure-report", type=Path)
    parser.add_argument("--reset-evidence", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--event-url", default="http://127.0.0.1:9092")
    args = parser.parse_args()

    scenario = load_native_scenario(args.scenario)
    prefix = load_json_strict(args.prefix)
    credentials = load_json_strict(args.credentials)
    if (
        scenario.family_id != "erpnext-multiwarehouse-transfer"
        or not isinstance(prefix, dict)
        or prefix.get("scenario_id") != scenario.scenario_id
        or args.variant not in scenario.variants
    ):
        raise ValueError("scenario, prefix and variant identity do not match")
    if (
        not isinstance(credentials, dict)
        or not credentials.get("api_key")
        or not credentials.get("api_secret")
    ):
        raise ValueError("ERPNext API credentials are incomplete")
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=str(credentials["api_key"]),
            api_secret=str(credentials["api_secret"]),
        )
    )
    payload = build_multiwarehouse_state_evidence(
        scenario_id=scenario.scenario_id,
        instance_id=scenario.instance_id,
        variant_id=args.variant,
        phase=args.phase,
        prefix_path=args.prefix,
        bundle_manifest_path=args.bundle_manifest,
        state=ERPNextMultiwarehouseEvidenceCollector(
            adapter, event_url=args.event_url
        ).collect(prefix),
        failure_report_path=args.failure_report,
        reset_evidence_path=args.reset_evidence,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario_id": scenario.scenario_id,
                "variant": args.variant,
                "phase": args.phase,
                "state_fingerprint": payload["state_fingerprint"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
