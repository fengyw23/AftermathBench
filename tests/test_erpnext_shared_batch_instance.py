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


class ERPNextSharedBatchInstanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = repository_root()
        self.spec_path = (
            self.root
            / "data"
            / "instance_specs"
            / "erpnext-shared-batch-recovery-dev-001.json"
        )
        self.blueprint_path = (
            self.root
            / "data"
            / "scenario_blueprints"
            / "erpnext-shared-batch-recovery-dev-001"
            / "scenario.json"
        )
        self.second_spec_path = (
            self.root
            / "data"
            / "instance_specs"
            / "erpnext-shared-batch-recovery-public-dev-002.json"
        )
        self.second_blueprint_path = (
            self.root
            / "data"
            / "scenario_blueprints"
            / "erpnext-shared-batch-recovery-public-dev-002"
            / "scenario.json"
        )

    def test_checked_blueprint_is_exactly_rendered_from_instance(self) -> None:
        instance = ERPNextNativeInstanceSpec.from_path(self.spec_path)
        checked = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
        rendered = render_erpnext_native_blueprint(
            instance,
            template=checked,
            instance_id="dev-001",
            benchmark_split="development",
        )
        self.assertEqual(rendered, checked)
        self.assertEqual(checked["instance_spec_sha256"], instance.sha256)
        self.assertEqual(
            checked["ambiguous_operation"]["operation"],
            "submit the prepared 3-unit corrective Job Card",
        )

    def test_fixture_proves_one_batch_can_supply_both_orders(self) -> None:
        instance = ERPNextNativeInstanceSpec.from_path(self.spec_path)
        fixture = instance.fixture
        required = (
            fixture["primary_work_order"]["ordered_quantity"]
            * fixture["primary_work_order"]["component_quantity_per_unit"]
            + fixture["secondary_work_order"]["ordered_quantity"]
            * fixture["secondary_work_order"]["component_quantity_per_unit"]
        )
        self.assertEqual(fixture["shared_component"]["received_quantity"], required)
        self.assertEqual(
            fixture["shared_landed_cost"]["primary_allocation"]
            + fixture["shared_landed_cost"]["secondary_allocation"],
            fixture["shared_landed_cost"]["amount"],
        )

    def test_second_instance_is_exactly_rendered_and_structurally_distinct(
        self,
    ) -> None:
        first = ERPNextNativeInstanceSpec.from_path(self.spec_path)
        second = ERPNextNativeInstanceSpec.from_path(self.second_spec_path)
        checked = json.loads(self.second_blueprint_path.read_text(encoding="utf-8"))
        rendered = render_erpnext_native_blueprint(
            second,
            template=checked,
            instance_id="public-dev-002",
            benchmark_split="public_dev",
        )
        self.assertEqual(rendered, checked)
        self.assertEqual(checked["instance_spec_sha256"], second.sha256)
        self.assertEqual(
            checked["ambiguous_operation"]["operation"],
            "submit the prepared 4-unit corrective Job Card",
        )
        first_fixture = first.fixture
        second_fixture = second.fixture
        self.assertNotEqual(
            first_fixture["primary_work_order"]["component_quantity_per_unit"],
            second_fixture["primary_work_order"]["component_quantity_per_unit"],
        )
        self.assertNotEqual(
            first_fixture["primary_work_order"]["rework_quantity"],
            second_fixture["primary_work_order"]["rework_quantity"],
        )
        first_codes = {
            first_fixture[key]["item_code"]
            for key in (
                "shared_component",
                "primary_work_order",
                "secondary_work_order",
                "unrelated_item",
            )
        }
        second_codes = {
            second_fixture[key]["item_code"]
            for key in (
                "shared_component",
                "primary_work_order",
                "secondary_work_order",
                "unrelated_item",
            )
        }
        self.assertTrue(first_codes.isdisjoint(second_codes))

    def test_rejects_a_batch_that_cannot_cover_both_orders(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["shared_component"]["received_quantity"] = 19
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly cover both work orders"):
                ERPNextNativeInstanceSpec.from_path(path)

    def test_rejects_primary_quantity_that_does_not_close(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["primary_work_order"]["rework_quantity"] = 2
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must close the order"):
                ERPNextNativeInstanceSpec.from_path(path)

    def test_rejects_shared_cost_that_does_not_reconcile(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["shared_landed_cost"]["secondary_allocation"] = 500
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must sum to the voucher"):
                ERPNextNativeInstanceSpec.from_path(path)

    def test_rejects_non_native_landed_cost_split(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["shared_landed_cost"]["primary_allocation"] = 900
        payload["fixture"]["shared_landed_cost"]["secondary_allocation"] = 540
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "amount-based"):
                ERPNextNativeInstanceSpec.from_path(path)

    def test_rejects_reservation_that_does_not_protect_secondary_output(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload = copy.deepcopy(payload)
        payload["fixture"]["customer_reservation"]["quantity"] = 7
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "protect all secondary output"):
                ERPNextNativeInstanceSpec.from_path(path)


if __name__ == "__main__":
    unittest.main()
