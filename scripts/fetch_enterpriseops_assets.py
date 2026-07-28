from __future__ import annotations

import argparse
import json

from aftermath_bench.integrations.enterprise_ops_assets import (
    ENTERPRISEOPS_ARCHIVE_SHA256,
    ENTERPRISEOPS_REVISION,
    fetch_enterpriseops_archive,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch the pinned EnterpriseOps-Gym seed archive."
    )
    parser.add_argument(
        "--destination",
        help="optional output path; defaults to the AftermathBench cache",
    )
    args = parser.parse_args()
    path = fetch_enterpriseops_archive(args.destination)
    print(json.dumps(
        {
            "revision": ENTERPRISEOPS_REVISION,
            "archive": str(path),
            "sha256": ENTERPRISEOPS_ARCHIVE_SHA256,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
