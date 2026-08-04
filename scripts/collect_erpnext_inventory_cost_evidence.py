from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_inventory_cost_evidence import (
    ERPNextInventoryCostEvidenceCollector,
)
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect native inventory-cost evidence.")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text(encoding="utf-8"))
    prefix = json.loads(args.prefix.read_text(encoding="utf-8"))
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=credentials["api_key"],
            api_secret=credentials["api_secret"],
        )
    )
    evidence = ERPNextInventoryCostEvidenceCollector(adapter).collect(prefix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), "keys": sorted(evidence)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
