from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_web import ForgejoWebSession


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _load(args.credentials)
    prefix = _load(args.prefix)
    session = ForgejoWebSession(
        base_url=credentials["web_base_url"],
        username=credentials["username"],
        password=credentials["password"],
    )
    history = session.webhook_history(
        prefix["owner"],
        prefix["repository"],
        int(prefix["webhook_id"]),
    )
    payload = {
        "schema_version": "0.1",
        "signed_in": session.signed_in,
        "webhook_id": prefix["webhook_id"],
        "history": [
            {"uuid": item.uuid, "status": item.status}
            for item in history
        ],
        "passed": session.signed_in and not history,
    }
    if not payload["passed"]:
        raise RuntimeError("Forgejo native webhook history validation failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
