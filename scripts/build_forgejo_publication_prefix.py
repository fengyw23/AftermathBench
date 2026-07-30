from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_publication_prefix import (
    ForgejoPublicationPrefixBuilder,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the native Forgejo publication prefix."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = json.loads(
        args.credentials.read_text(encoding="utf-8")
    )
    prefix = ForgejoPublicationPrefixBuilder(
        ForgejoAPI(
            base_url=credentials["base_url"],
            token=credentials["token"],
        )
    ).build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(prefix.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "scenario_id": "forgejo-release-publication-dev-002",
                "prefix_writes": len(prefix.trace),
                "expected_assets": len(prefix.expected_assets),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
