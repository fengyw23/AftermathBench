from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.erpnext_manufacturing_formal_build_spec import (
    generate_erpnext_manufacturing_formal_build_spec,
    write_erpnext_manufacturing_formal_build_spec,
)
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a seven-role formal-evidence build spec from exact "
            "ERPNext manufacturing recovery evidence."
        )
    )
    parser.add_argument("--phase", required=True, choices=("inputs", "complete"))
    parser.add_argument("--benchmark-release-id", required=True)
    parser.add_argument("--scenario", type=Path)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--capture-directory", type=Path, required=True)
    parser.add_argument(
        "--capture-bundle-manifest",
        type=Path,
        action="append",
        required=True,
    )
    parser.add_argument("--control-manifest", type=Path)
    parser.add_argument("--model-input-lock", type=Path)
    parser.add_argument("--formal-output-directory", required=True)
    parser.add_argument("--output-spec", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=repository_root())
    args = parser.parse_args()
    result = generate_erpnext_manufacturing_formal_build_spec(
        root=args.root,
        benchmark_release_id=args.benchmark_release_id,
        output_directory=args.formal_output_directory,
        runtime_manifest_path=args.runtime_manifest,
        capture_directory=args.capture_directory,
        capture_bundle_manifest_paths=args.capture_bundle_manifest,
        phase=args.phase,
        scenario_path=args.scenario,
        control_manifest_path=args.control_manifest,
        model_input_lock_path=args.model_input_lock,
    )
    output = write_erpnext_manufacturing_formal_build_spec(
        args.output_spec,
        result.spec,
        root=args.root,
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "output_spec": output,
                "scenario_path": result.scenario_path,
                "runtime_manifest_path": result.runtime_manifest_path,
                "control_manifest_path": result.control_manifest_path,
                "capture_bundle_manifest_paths": list(
                    result.capture_bundle_manifest_paths
                ),
                "variant_count": len(result.spec["variant_ids"]),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
