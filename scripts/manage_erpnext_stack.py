from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_stack import ERPNextStack
from aftermath_bench.schema import repository_root


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage the pinned native ERPNext benchmark stack."
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
    root = repository_root()
    runtime = root / "runtimes" / "erpnext"
    stack = ERPNextStack(
        compose_file=runtime / "compose.yaml",
        container_cli=args.container_cli,
        db_root_password=os.environ.get(
            "AFTERMATH_DB_ROOT_PASSWORD",
            "aftermath-root",
        ),
    )
    if args.action == "up":
        stack.up()
    elif args.action == "setup":
        stack.setup_company()
        keys = stack.generate_administrator_keys()
        credentials = runtime / ".runtime" / "credentials.json"
        credentials.parent.mkdir(parents=True, exist_ok=True)
        credentials.write_text(json.dumps(keys, indent=2), encoding="utf-8")
        os.chmod(credentials, 0o600)
        print(f"credentials written to {credentials}")
    elif args.action == "snapshot":
        if not args.snapshot:
            parser.error("--snapshot is required")
        digest = stack.snapshot_database(args.snapshot)
        print(json.dumps({"snapshot": str(args.snapshot), "sha256": digest}))
    elif args.action == "restore":
        if not args.snapshot:
            parser.error("--snapshot is required")
        stack.restore_database(args.snapshot)
    elif args.action == "down":
        stack.down()
    else:
        stack.down(remove_volumes=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

