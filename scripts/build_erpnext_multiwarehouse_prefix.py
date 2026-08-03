from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_multiwarehouse_prefix import (
    ERPNextMultiwarehousePrefixBuilder,
)
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the native ERPNext multiwarehouse failure prefix."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenario = json.loads(args.scenario.read_text(encoding="utf-8"))
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=os.environ["FRAPPE_BASE_URL"],
            api_key=os.environ["FRAPPE_API_KEY"],
            api_secret=os.environ["FRAPPE_API_SECRET"],
        )
    )
    prefix = ERPNextMultiwarehousePrefixBuilder(
        adapter,
        scenario_id=str(scenario["scenario_id"]),
        fixture=scenario["fixture"],
    ).build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(prefix.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(prefix.as_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
