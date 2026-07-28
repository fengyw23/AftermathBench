from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aftermath_bench.integrations.erpnext_prefix import (
    ERPNextProcurementPrefixBuilder,
)
from aftermath_bench.integrations.frappe import (
    FrappeConfig,
    FrappeHTTPAdapter,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the ERPNext procurement prefix through public APIs."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--api-key-env", default="AFTERMATH_FRAPPE_API_KEY")
    parser.add_argument(
        "--api-secret-env",
        default="AFTERMATH_FRAPPE_API_SECRET",
    )
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stored = (
        json.loads(args.credentials.read_text(encoding="utf-8"))
        if args.credentials
        else {}
    )
    api_key = stored.get("api_key") or os.environ.get(args.api_key_env)
    api_secret = stored.get("api_secret") or os.environ.get(args.api_secret_env)
    if not api_key or not api_secret:
        parser.error(
            f"{args.api_key_env} and {args.api_secret_env} must be set"
        )
    adapter = FrappeHTTPAdapter(
        FrappeConfig(
            base_url=args.base_url,
            api_key=api_key,
            api_secret=api_secret,
        )
    )
    builder = ERPNextProcurementPrefixBuilder(adapter)
    builder.prepare_public_fixture()
    prefix = builder.build()
    payload = {
        "purchase_order": prefix.purchase_order,
        "purchase_receipt": prefix.purchase_receipt,
        "purchase_invoice": prefix.purchase_invoice,
        "payment_entry": prefix.payment_entry,
        "protected_fingerprints": prefix.protected_fingerprints,
        "trace": prefix.trace,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
