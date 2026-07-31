from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_publication_prefix import (
    ForgejoPublicationPrefixBuilder,
)
from aftermath_bench.integrations.forgejo_publication_instance import (
    ForgejoPublicationInstanceSpec,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the native Forgejo publication prefix."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    credentials = json.loads(
        args.credentials.read_text(encoding="utf-8")
    )
    instance = ForgejoPublicationInstanceSpec.from_path(args.instance_spec)
    if credentials.get("username") != instance.owner:
        raise ValueError(
            "instance owner does not match the authenticated Forgejo user"
        )
    prefix = ForgejoPublicationPrefixBuilder(
        ForgejoAPI(
            base_url=credentials["base_url"],
            token=credentials["token"],
        ),
        instance,
    ).build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(prefix.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "scenario_id": prefix.scenario_id,
                "instance_spec_sha256": prefix.instance_spec_sha256,
                "prefix_writes": len(prefix.trace),
                "expected_assets": len(prefix.expected_assets),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
