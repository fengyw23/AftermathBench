from __future__ import annotations

import argparse
import json
import os
import secrets
from pathlib import Path

from aftermath_bench.integrations.forgejo_stack import ForgejoStack


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Issue ephemeral credentials after restoring a frozen Forgejo "
            "state bundle. This changes authentication control state only."
        )
    )
    parser.add_argument("--compose-file", type=Path, required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--token-name",
        default="aftermath-hidden-evaluation",
    )
    parser.add_argument(
        "--container-cli",
        choices=("docker", "podman"),
        default="docker",
    )
    args = parser.parse_args()

    stack = ForgejoStack(
        compose_file=args.compose_file.resolve(),
        container_cli=args.container_cli,
    )
    password = secrets.token_urlsafe(32)
    stack.run(
        "exec",
        "-T",
        "-u",
        "git",
        "forgejo",
        "forgejo",
        "admin",
        "user",
        "change-password",
        "--username",
        args.username,
        "--password",
        password,
        "--must-change-password=false",
        capture_output=True,
    )
    token_result = stack.run(
        "exec",
        "-T",
        "-u",
        "git",
        "forgejo",
        "forgejo",
        "admin",
        "user",
        "generate-access-token",
        "--username",
        args.username,
        "--token-name",
        args.token_name,
        "--scopes",
        "all",
        "--raw",
        capture_output=True,
    )
    token = token_result.stdout.strip()
    if not token or any(character.isspace() for character in token):
        raise RuntimeError("Forgejo did not return one raw access token")
    credentials = {
        "base_url": "http://127.0.0.1:8080/api/v1",
        "web_base_url": "http://127.0.0.1:8080",
        "username": args.username,
        "password": password,
        "token": token,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(credentials, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.chmod(args.output, 0o600)
    print(
        json.dumps(
            {
                "credentials_written": str(args.output),
                "username": args.username,
                "control_plane_only": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
