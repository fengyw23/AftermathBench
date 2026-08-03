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


class ERPNextNativeInstanceTests(unittest.TestCase):
    def _instance(self) -> ERPNextNativeInstanceSpec:
        return ERPNextNativeInstanceSpec(
            schema_version="1.0",
            scenario_id="erpnext-manufacturing-rework-hidden-test-001",
            family="erpnext-manufacturing-rework",
            title="Recover a private manufacturing instance",
            user_instruction="Preserve accepted output and complete correction.",
            fixture={
                "rework_quantity": 2,
                **{f"field_{index}": index for index in range(5)},
            },
        )

    def test_hidden_render_binds_instance_without_mutating_template(self) -> None:
        instance = self._instance()
        template = {
            "scenario_id": "public",
            "family": instance.family,
            "benchmark_split": "public_dev",
            "hidden_test_eligible": False,
            "fixture": {"public": True},
            "ambiguous_operation": {
                "operation": "submit a prepared corrective Job Card",
                "surface_result": "connection lost",
            },
            "matched_variants": [{"id": "boundary"}],
        }
        original = copy.deepcopy(template)
        rendered = render_erpnext_native_blueprint(
            instance,
            template=template,
            instance_id="test-001",
            benchmark_split="hidden_test",
        )
        self.assertEqual(template, original)
        self.assertEqual(rendered["scenario_id"], instance.scenario_id)
        self.assertEqual(rendered["benchmark_split"], "hidden_test")
        self.assertTrue(rendered["hidden_test_eligible"])
        self.assertEqual(rendered["instance_spec_sha256"], instance.sha256)
        self.assertEqual(rendered["matched_variants"], [{"id": "boundary"}])

    def test_loader_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "instance.json"
            payload = self._instance().as_dict()
            payload["hidden_answer"] = "not allowed"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "fields"):
                ERPNextNativeInstanceSpec.from_path(path)

    def test_manufacturing_operation_tracks_instance_quantity(self) -> None:
        instance = ERPNextNativeInstanceSpec(
            schema_version="1.0",
            scenario_id="erpnext-manufacturing-rework-public-dev-002",
            family="erpnext-manufacturing-rework",
            title="Recover a public manufacturing instance",
            user_instruction="Preserve nine units and rework three units.",
            fixture={
                "rework_quantity": 3,
                **{f"field_{index}": index for index in range(5)},
            },
        )
        rendered = render_erpnext_native_blueprint(
            instance,
            template={
                "family": instance.family,
                "ambiguous_operation": {
                    "operation": "template-specific stale quantity",
                    "surface_result": "connection lost",
                },
            },
            instance_id="dev-002",
            benchmark_split="public_dev",
        )
        self.assertEqual(
            rendered["ambiguous_operation"]["operation"],
            "submit the prepared 3-unit corrective Job Card",
        )


if __name__ == "__main__":
    unittest.main()
