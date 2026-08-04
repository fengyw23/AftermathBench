from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_shared_batch_evidence import (
    ERPNextSharedBatchEvidenceCollector,
)
from aftermath_bench.integrations.frappe import FrappeConfig, FrappeHTTPAdapter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect raw ERPNext shared-batch native evidence."
    )
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--event-url", default="http://127.0.0.1:9092")
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
    evidence = ERPNextSharedBatchEvidenceCollector(
        adapter, event_url=args.event_url
    ).collect(prefix)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
