from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_runtime import (
    create_build_plan,
    execute_build_plan,
)


def _default_source_directory() -> Path:
    configured = os.environ.get("AFTERMATH_SCRATCH")
    if configured:
        return Path(configured) / "erpnext-runtime" / "frappe_docker"
    if os.name == "nt":
        return Path("D:/Codex/scratch/aftermathbench-runtime/frappe_docker")
    return Path("/tmp/aftermathbench-runtime/frappe_docker")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the pinned ERPNext/Frappe image from public source."
    )
    parser.add_argument(
        "--source-directory",
        type=Path,
        default=_default_source_directory(),
    )
    parser.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run the pinned fetch and image build; default is a dry run",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Write the exact build and source-verification report.",
    )
    args = parser.parse_args()
    plan = create_build_plan(
        args.source_directory,
        container_cli=args.container_cli,
    )
    payload: dict = {"plan": plan.as_dict()}
    if args.execute:
        image_build = execute_build_plan(plan)
        payload["source_verification"] = {
            "build_driver_revision": plan.expected_driver_revision,
            "source_refs": image_build["verified_source_refs"],
            "passed": True,
        }
        payload["image_build"] = image_build
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

