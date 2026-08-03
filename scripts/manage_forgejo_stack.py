from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path

from aftermath_bench.integrations.forgejo_stack import ForgejoStack
from aftermath_bench.schema import repository_root


def _administrator_password() -> str:
    configured = os.environ.get("AFTERMATH_FORGEJO_ADMIN_PASSWORD")
    return configured if configured else secrets.token_urlsafe(32)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage the pinned native Forgejo benchmark stack."
    )
    parser.add_argument(
        "action",
        choices=(
            "up",
            "setup",
            "setup-runner",
            "snapshot",
            "restore",
            "snapshot-bundle",
            "restore-bundle",
            "down",
            "purge",
        ),
    )
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    parser.add_argument(
        "--username",
        default="aftermath",
        help="administrator/login owner created by the setup action",
    )
    parser.add_argument(
        "--email",
        default="admin@aftermath.invalid",
        help="administrator email created by the setup action",
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
            username=args.username,
            password=_administrator_password(),
            email=args.email,
        )
        path = runtime / ".runtime" / "credentials.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(credentials, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(path, 0o600)
        print(f"credentials written to {path}")
    elif args.action == "setup-runner":
        stack.register_action_runner()
        print("pinned Forgejo Actions runner registered")
    elif args.action == "snapshot":
        if not args.snapshot:
            parser.error("--snapshot is required")
        digest = stack.snapshot(args.snapshot)
        print(json.dumps({"snapshot": str(args.snapshot), "sha256": digest}))
    elif args.action == "restore":
        if not args.snapshot:
            parser.error("--snapshot is required")
        stack.restore(args.snapshot)
    elif args.action == "snapshot-bundle":
        if not args.snapshot:
            parser.error("--snapshot is required")
        print(json.dumps(stack.snapshot_bundle(args.snapshot)))
    elif args.action == "restore-bundle":
        if not args.snapshot:
            parser.error("--snapshot is required")
        stack.restore_bundle(args.snapshot)
    elif args.action == "down":
        stack.down()
    else:
        stack.down(remove_volumes=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
