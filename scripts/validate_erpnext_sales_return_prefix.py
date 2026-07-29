from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.integrations.erpnext_sales_return_evidence import (
    ERPNextSalesReturnEvidenceCollector,
)
from aftermath_bench.integrations.frappe import (
    FrappeConfig,
    FrappeHTTPAdapter,
)


def validate_prefix(
    prefix: dict,
    evidence: dict,
) -> dict:
    payment_references = {
        str(row.get("reference_name"))
        for row in evidence["shared_payment_entry"].get("references", [])
    }
    stock_vouchers = {
        str(row.get("voucher_no")) for row in evidence.get("stock_ledger_entries", [])
    }
    checks = {
        "at_least_eighteen_successful_prefix_writes": sum(
            event.get("kind") == "write" and event.get("status") == "success"
            for event in prefix.get("trace", [])
        )
        >= 18,
        "original_sales_order_submitted": int(
            evidence["original_sales_order"].get("docstatus", 0)
        )
        == 1,
        "original_delivery_submitted": int(
            evidence["original_delivery_note"].get("docstatus", 0)
        )
        == 1,
        "quality_inspection_rejected": (
            int(evidence["quality_inspection"].get("docstatus", 0)) == 1
            and evidence["quality_inspection"].get("status") == "Rejected"
        ),
        "both_original_invoices_submitted": all(
            int(evidence[key].get("docstatus", 0)) == 1
            for key in ("affected_invoice", "unaffected_invoice")
        ),
        "shared_payment_submitted": int(
            evidence["shared_payment_entry"].get("docstatus", 0)
        )
        == 1,
        "shared_payment_references_both_invoices": {
            str(prefix["affected_invoice"]),
            str(prefix["unaffected_invoice"]),
        }.issubset(payment_references),
        "partial_sales_return_is_draft": int(
            evidence["sales_return"].get("docstatus", -1)
        )
        == 0,
        "credit_note_is_draft": int(evidence["credit_note"].get("docstatus", -1)) == 0,
        "replacement_order_submitted": int(
            evidence["replacement_sales_order"].get("docstatus", 0)
        )
        == 1,
        "replacement_delivery_is_draft": int(
            evidence["replacement_delivery_note"].get("docstatus", -1)
        )
        == 0,
        "replacement_invoice_not_yet_created": not evidence.get("replacement_invoices"),
        "original_delivery_has_stock_ledger": str(prefix["original_delivery_note"])
        in stock_vouchers,
        "no_pickup_before_return_submit": evidence.get("pickup_delivery") is None,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path)
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
    evidence = ERPNextSalesReturnEvidenceCollector(adapter).collect(prefix)
    result = validate_prefix(prefix, evidence)
    payload = {"validation": result, "evidence": evidence}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
