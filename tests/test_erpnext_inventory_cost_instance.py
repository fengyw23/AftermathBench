from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.erpnext_native_instance import (
    ERPNextNativeInstanceSpec,
    render_erpnext_native_blueprint,
)
from aftermath_bench.schema import repository_root


class ERPNextInventoryCostInstanceTest(unittest.TestCase):
    def setUp(self) -> None:
        root = repository_root()
        self.spec_path = (
            root
            / "data"
            / "instance_specs"
            / "erpnext-inventory-cost-settlement-public-dev-001.json"
        )
        self.blueprint_path = (
            root
            / "data"
            / "scenario_blueprints"
            / "erpnext-inventory-cost-settlement-public-dev-001"
            / "scenario.json"
        )

    def _rejects(self, payload: dict[str, object], pattern: str) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, pattern):
                ERPNextNativeInstanceSpec.from_path(path)

    def test_checked_blueprint_is_exactly_rendered_from_instance(self) -> None:
        instance = ERPNextNativeInstanceSpec.from_path(self.spec_path)
        checked = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
        rendered = render_erpnext_native_blueprint(
            instance,
            template=checked,
            instance_id="public-dev-001",
            benchmark_split="public_dev",
        )
        self.assertEqual(rendered, checked)
        self.assertEqual(checked["instance_spec_sha256"], instance.sha256)
        self.assertEqual(
            checked["ambiguous_operation"]["operation"],
            "submit the prepared USD 1,200.00 Landed Cost Voucher",
        )
        self.assertEqual(len(checked["state_dimensions_that_must_vary"]), 5)

    def test_rejects_uncovered_consumption(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["shared_component"]["received_quantity"] = 19
        self._rejects(payload, "exactly cover both production branches")

    def test_rejects_non_native_cost_allocation(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["landed_cost"]["primary_allocation"] = 600
        payload["fixture"]["landed_cost"]["secondary_allocation"] = 600
        self._rejects(payload, "amount-based distribution")

    def test_rejects_unbound_attestation_or_reservation(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["external_attestation"]["landed_cost_amount"] = 1000
        self._rejects(payload, "bind the full landed-cost amount")

        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["customer_reservation"]["quantity"] = 7
        self._rejects(payload, "protect the secondary output")


if __name__ == "__main__":
    unittest.main()
