from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.forgejo_runtime import (
    checkout_and_verify,
    create_build_plan,
    execute_build,
)


def _default_source_directory() -> Path:
    configured = os.environ.get("AFTERMATH_SCRATCH")
    if configured:
        return Path(configured) / "forgejo-runtime" / "forgejo"
    if os.name == "nt":
        return Path("D:/Codex/scratch/aftermathbench-runtime/forgejo")
    return Path("/tmp/aftermathbench-runtime/forgejo")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify and build the pinned Forgejo server from source."
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
        "--checkout",
        action="store_true",
        help="fetch the pinned revision and verify every audited source hash",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="build the image after a verified checkout",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    plan = create_build_plan(
        args.source_directory,
        container_cli=args.container_cli,
    )
    payload: dict = {"plan": plan.as_dict()}
    if args.checkout:
        payload["source_verification"] = checkout_and_verify(plan)
    if args.build:
        execute_build(plan)
        payload["image_built"] = True
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
