from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify restored Forgejo API-token and web credentials."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    user = ForgejoAPI(
        base_url=credentials["base_url"],
        token=credentials["token"],
    ).get("/user")
    api_passed = (
        isinstance(user, dict)
        and str(user.get("login", "")) == credentials["username"]
    )
    web = ForgejoWebSession(
        base_url=credentials["web_base_url"],
        username=credentials["username"],
        password=credentials["password"],
    )
    web.login()
    payload = {
        "schema_version": "1.0",
        "api_token_passed": api_passed,
        "web_login_passed": web.signed_in,
    }
    if not all(payload.values()):
        raise RuntimeError("restored Forgejo credential smoke check failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
