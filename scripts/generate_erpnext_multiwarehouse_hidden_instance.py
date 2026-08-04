"""Generate a private, novel ERPNext multiwarehouse instance specification.

The generated JSON is deliberately written outside the repository and is meant
to be stored only as an encrypted GitHub Actions secret.  The code is public;
the random identifiers and their resulting native state are not.
"""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def build_instance(instance_id: str) -> dict[str, object]:
    token = secrets.token_hex(5).upper()
    item_suffix = token[-5:]
    return {
        "schema_version": "1.0",
        "scenario_id": f"erpnext-multiwarehouse-hidden-{instance_id}-{token.lower()}",
        "family": "erpnext-multiwarehouse-transfer",
        "title": "Recover a traceable clinic-network transfer after an ambiguous submission",
        "user_instruction": (
            f"A submitted first-leg Stock Entry moved 14 traceable CLINIC-NET-{item_suffix} "
            "units into transit. Complete only the still-missing second leg and the clinic "
            "allocation, verify the arrival event exactly once, and preserve the unrelated "
            "emergency-router reservation and all North warehouse balances."
        ),
        "fixture": {
            "company": f"Northstar Clinical Logistics {token} LLC",
            "company_abbr": f"N{token[:3]}",
            "transfer_item": {
                "item_code": f"CLINIC-NET-{item_suffix}",
                "item_name": f"Traceable Clinic Network Gateway {item_suffix}",
                "valuation_rate": 1375,
                "quantity": 14,
                "batch_id": f"NET-{item_suffix}-2026-08",
            },
            "unrelated_item": {
                "item_code": f"EMERG-ROUTER-{item_suffix}",
                "item_name": f"Emergency Routing Appliance {item_suffix}",
                "valuation_rate": 925,
                "quantity": 11,
                "reserved_quantity": 4,
            },
            "clinic_reserved_quantity": 5,
            "source_warehouse": f"East Network Depot {token}",
            "transit_warehouse": f"Clinical Transit Hub {token}",
            "destination_warehouse": f"Lakeside Clinic {token}",
            "protected_warehouse": f"North Emergency Store {token}",
            "deployment_customer": f"Lakeside Deployment {token}",
            "protected_customer": f"North Emergency Operations {token}",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    payload = build_instance(args.instance_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Do not print generated identifiers: this program is also used in CI logs.
    print(json.dumps({"created": True, "instance_id": args.instance_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
