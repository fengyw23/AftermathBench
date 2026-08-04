from __future__ import annotations

import argparse
import json
from pathlib import Path

from aftermath_bench.independent_gap_design import build_independent_gap_design


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the strict pre-runtime ERPNext reconciliation design."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_independent_gap_design(
        scenario_id="erpnext-inventory-reconciliation-dev-001",
        obligations={
            "landed_cost_matches_receipts": (
                "purchase_receipts",
                "landed_cost_voucher",
            ),
            "stock_valuation_matches_landed_cost": (
                "landed_cost_voucher",
                "stock_ledger",
            ),
            "general_ledger_matches_stock_valuation": (
                "stock_ledger",
                "general_ledger",
            ),
            "reservation_matches_available_valued_stock": (
                "stock_ledger",
                "sales_reservation",
            ),
            "settlement_attestation_matches_final_ledgers": (
                "landed_cost_voucher",
                "general_ledger",
                "external_attestation",
            ),
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(payload["observed"], ensure_ascii=False))
    return 0 if payload["passed_design_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
