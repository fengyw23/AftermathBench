from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_sales_return_prefix import (
    ERPNextSalesReturnPrefixBuilder,
)
from aftermath_bench.integrations.frappe import (
    FrappeConfig,
    FrappeHTTPAdapter,
)
from aftermath_bench.native_scenario import load_native_scenario


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the native ERPNext sales-return prefix."
    )
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    scenario = load_native_scenario(args.scenario)
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    prefix = ERPNextSalesReturnPrefixBuilder(
        adapter,
        scenario_id=scenario.scenario_id,
        fixture=scenario.raw["fixture"],
    ).build()
    payload = prefix.as_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
