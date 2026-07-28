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
    args = parser.parse_args()
    plan = create_build_plan(
        args.source_directory,
        container_cli=args.container_cli,
    )
    print(json.dumps(plan.as_dict(), indent=2))
    if args.execute:
        execute_build_plan(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

