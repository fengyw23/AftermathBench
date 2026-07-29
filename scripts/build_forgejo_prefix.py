from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_prefix import (
    ForgejoReleasePrefixBuilder,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the native Forgejo Pull Request recovery prefix."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = _load(args.credentials)
    prefix = ForgejoReleasePrefixBuilder(
        ForgejoAPI(
            base_url=str(credentials["base_url"]),
            token=str(credentials["token"]),
        )
    ).build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(prefix.as_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario_id": "forgejo-pr-release-dev-001",
                "successful_prefix_writes": len(prefix.trace),
                "output": str(args.output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
