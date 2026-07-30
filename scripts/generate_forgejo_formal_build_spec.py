from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.forgejo_formal_build_spec import (
    generate_forgejo_formal_build_spec,
    write_forgejo_formal_build_spec,
)
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a seven-role formal-evidence build spec from strictly "
            "validated Forgejo public-dev evidence. This command neither "
            "builds formal evidence nor edits the release manifest."
        )
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=("inputs", "complete"),
        help=(
            "inputs freezes the five pre-model roles; complete additionally "
            "binds the formal input lock and execution-control archive."
        ),
    )
    parser.add_argument(
        "--benchmark-release-id",
        required=True,
        help="Canonical benchmark release identifier.",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        help=(
            "Active admitted Forgejo public_dev scenario. If omitted, the "
            "repository must contain exactly one matching scenario."
        ),
    )
    parser.add_argument(
        "--runtime-manifest",
        type=Path,
        required=True,
        help=(
            "Exact files.json for the native runtime bundle containing "
            "runtime/<variant>-boundary.json and -reference.json."
        ),
    )
    parser.add_argument(
        "--capture-directory",
        type=Path,
        required=True,
        help=(
            "Directory containing <variant>-reset.json and "
            "<variant>-boundary.json."
        ),
    )
    parser.add_argument(
        "--capture-bundle-manifest",
        type=Path,
        action="append",
        required=True,
        help=(
            "Exact simultaneous-quiescence bundle.json used by captures. "
            "Repeat for every distinct bundle manifest."
        ),
    )
    parser.add_argument(
        "--control-manifest",
        type=Path,
        help=(
            "Exact files.json for model-runs/repetition-01 and summary.json; "
            "required only in complete phase."
        ),
    )
    parser.add_argument(
        "--model-input-lock",
        type=Path,
        help=(
            "The phase-input output/formal-input-lock.json; required only "
            "in complete phase."
        ),
    )
    parser.add_argument(
        "--formal-output-directory",
        required=True,
        help="Immutable formal package directory below data/.",
    )
    parser.add_argument(
        "--output-spec",
        type=Path,
        required=True,
        help=(
            "New JSON file to receive the build spec. Use separate input and "
            "complete spec files; existing files are never overwritten."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=repository_root(),
        help="Repository root (defaults to the installed checkout).",
    )
    args = parser.parse_args()
    result = generate_forgejo_formal_build_spec(
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
    output = write_forgejo_formal_build_spec(
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
                "tool_count": len(
                    result.spec["roles"]["tool_contract"][
                        "primary_payload"
                    ]["tools"]
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
