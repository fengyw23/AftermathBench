from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.deployment_target_api import DeploymentTargetAPI
from aftermath_bench.integrations.forgejo_api import ForgejoAPI
from aftermath_bench.integrations.forgejo_migration_instance import (
    ForgejoMigrationInstanceSpec,
)
from aftermath_bench.integrations.forgejo_migration_prefix import (
    ForgejoMigrationPrefixBuilder,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the native Forgejo Actions migration prefix."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--instance-spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--deployment-url", default="http://127.0.0.1:9095"
    )
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    instance = ForgejoMigrationInstanceSpec.from_path(args.instance_spec)
    if credentials.get("username") != instance.owner:
        raise ValueError(
            "instance owner does not match the authenticated Forgejo user"
        )
    prefix = ForgejoMigrationPrefixBuilder(
        ForgejoAPI(
            base_url=str(credentials["base_url"]),
            token=str(credentials["token"]),
        ),
        DeploymentTargetAPI(args.deployment_url),
        instance,
    ).build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(prefix.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "scenario_id": prefix.scenario_id,
                "instance_spec_sha256": prefix.instance_spec_sha256,
                "prefix_writes": len(prefix.trace),
                "source_commit": prefix.source_commit,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
