"""Generate a private, novel ERPNext partial-return recovery instance."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def build_instance(instance_id: str) -> dict[str, object]:
    token = secrets.token_hex(5).upper()
    suffix = token[-5:]
    defective = 3 + int(token[-1], 16) % 3
    total = defective + 7 + int(token[-2], 16) % 5
    unit_price = 1325 + (int(token[-3:-1], 16) % 6) * 125
    return {
        "scenario_id": f"erpnext-sales-return-hidden-{instance_id}-{token.lower()}",
        "customer": f"Northstar Mobile Diagnostics {suffix}",
        "affected_item": {
            "item_code": f"RAD-TABLET-{suffix}",
            "item_name": f"Rugged Radiology Tablet {suffix}",
            "quantity": total,
            "defective_quantity": defective,
            "unit_price": unit_price,
        },
        "unaffected_item": {
            "item_code": f"CLINIC-ROUTER-{suffix}",
            "item_name": f"Mobile Clinic Router {suffix}",
            "quantity": 2 + int(token[-4], 16) % 3,
            "unit_price": 875 + (int(token[-5], 16) % 5) * 100,
        },
        "replacement_item": {
            "item_code": f"RAD-TABLET-R2-{suffix}",
            "item_name": f"Approved Radiology Tablet R2 {suffix}",
            "quantity": defective,
            "unit_price": unit_price,
            "replaces": f"RAD-TABLET-{suffix}",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_instance(args.instance_id), indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"created": True, "instance_id": args.instance_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
