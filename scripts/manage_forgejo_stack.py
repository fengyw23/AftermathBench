from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.forgejo_stack import ForgejoStack
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage the pinned native Forgejo benchmark stack."
    )
    parser.add_argument(
        "action",
        choices=("up", "setup", "snapshot", "restore", "down", "purge"),
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    args = parser.parse_args()
    runtime = repository_root() / "runtimes" / "forgejo"
    stack = ForgejoStack(
        compose_file=runtime / "compose.yaml",
        container_cli=args.container_cli,
    )
    if args.action == "up":
        stack.up()
    elif args.action == "setup":
        credentials = stack.create_administrator(
            password=os.environ.get(
                "AFTERMATH_FORGEJO_ADMIN_PASSWORD",
                "aftermath-admin",
            )
        )
        path = runtime / ".runtime" / "credentials.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(credentials, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(path, 0o600)
        print(f"credentials written to {path}")
    elif args.action == "snapshot":
        if not args.snapshot:
            parser.error("--snapshot is required")
        digest = stack.snapshot(args.snapshot)
        print(json.dumps({"snapshot": str(args.snapshot), "sha256": digest}))
    elif args.action == "restore":
        if not args.snapshot:
            parser.error("--snapshot is required")
        stack.restore(args.snapshot)
    elif args.action == "down":
        stack.down()
    else:
        stack.down(remove_volumes=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
