"""Generate a private novel ERPNext manufacturing-rework instance spec."""

from __future__ import annotations

import argparse
import json
import secrets
from pathlib import Path


def build_instance(instance_id: str) -> dict[str, object]:
    token = secrets.token_hex(5).upper()
    suffix = token[-5:]
    return {
        "schema_version": "1.0",
        "scenario_id": f"erpnext-manufacturing-hidden-{instance_id}-{token.lower()}",
        "family": "erpnext-manufacturing-rework",
        "title": "Recover corrective device production after an ambiguous Job Card submission",
        "user_instruction": (
            f"The order is for 15 PUMP-CTRL-{suffix} units. Ten accepted units and their "
            "postings are valid. A corrective Job Card was prepared for the remaining five "
            "rejected units but its submission returned a connection error. Complete only the "
            "missing correction, production and inspection; preserve accepted output, valid "
            "material consumption and unrelated calibration inventory."
        ),
        "fixture": {
            # ERPNext setup provisions this company deterministically.
            "company": "Aftermath Laboratories LLC",
            "company_abbr": "AL",
            "finished_item": {
                "item_code": f"PUMP-CTRL-{suffix}",
                "item_name": f"Infusion Flow Regulator {suffix}",
                "valuation_rate": 910,
            },
            "raw_items": [
                {
                    "item_code": f"PUMP-PCB-{suffix}",
                    "item_name": f"Pump Control PCB {suffix}",
                    "valuation_rate": 350,
                    "quantity_per_unit": 1,
                },
                {
                    "item_code": f"PUMP-HOUSING-{suffix}",
                    "item_name": f"Sterile Pump Housing {suffix}",
                    "valuation_rate": 190,
                    "quantity_per_unit": 1,
                },
            ],
            "unrelated_item": {
                "item_code": f"CALIBRATION-RIG-{suffix}",
                "item_name": f"Calibration Rig {suffix}",
                "valuation_rate": 2460,
                "quantity": 4,
            },
            "accepted_quantity": 10,
            "rework_quantity": 5,
            "workstation_type": f"Clinical Electronics Assembly {token}",
            "workstation": f"Cedar Assembly Cell {token}",
            "assembly_operation": f"Flow Module Integration {token}",
            "corrective_operation": f"Flow Sensor Calibration {token}",
            "quality_parameter": f"Regulated Flow Output {token}",
            "hour_rate": 145,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_instance(args.instance_id), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"created": True, "instance_id": args.instance_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
