import copy
import json
import unittest
from pathlib import Path

from aftermath_bench.erpnext_formal_build_spec import (
    ERPNextFormalBuildSpecError,
    _evaluator_role,
    _tool_role,
    _validate_reference,
)
from aftermath_bench.integrations.erpnext_sales_return_evaluator import (
    evaluate_sales_return_recovery,
)
from aftermath_bench.native_scenario import load_native_scenario


class ERPNextFormalBuildSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.scenario = load_native_scenario(
            cls.root
            / "data"
            / "scenarios"
            / "erpnext-sales-return-dev-001"
            / "scenario.json"
        )
        cls.prefix = json.loads(
            cls.scenario.resolve_artifact("prefix").read_text(
                encoding="utf-8"
            )
        )
        cls.reference_path = (
            cls.root
            / "data"
            / "evidence"
            / "erpnext-sales-return-native-historical-30425865276"
            / "raw"
            / "references"
            / "request_not_reached-reference.json"
        )

    def _formal_reference(self) -> dict:
        payload = json.loads(
            self.reference_path.read_text(encoding="utf-8")
        )
        payload["schema_version"] = "1.0"
        payload["artifact_type"] = (
            "erpnext_sales_return_reference_recovery"
        )
        payload["phase"] = "reference"
        evaluation = evaluate_sales_return_recovery(
            payload["final_evidence"],
            prefix=self.prefix,
        )
        payload["evaluation"] = {
            "passed": evaluation.passed,
            "components": evaluation.components,
            "checks": evaluation.checks,
            "diagnostics": evaluation.diagnostics,
            "failures": list(evaluation.failures),
        }
        return payload

    def test_reference_is_recomputed_from_final_native_evidence(self) -> None:
        payload = self._formal_reference()
        checks = _validate_reference(
            payload,
            prefix=self.prefix,
            scenario=self.scenario,
            variant_id="request_not_reached",
        )
        self.assertEqual(len(checks), 19)
        self.assertIn("no_duplicate_sales_return", checks)

    def test_reference_rejects_a_forged_pass_result(self) -> None:
        payload = self._formal_reference()
        payload["evaluation"]["checks"][
            "no_duplicate_sales_return"
        ] = False
        with self.assertRaises(ERPNextFormalBuildSpecError):
            _validate_reference(
                payload,
                prefix=self.prefix,
                scenario=self.scenario,
                variant_id="request_not_reached",
            )

    def test_shared_roles_describe_the_exact_public_surface(self) -> None:
        tool_role = _tool_role(
            root=self.root,
            output="data/evidence/formal/test/erpnext",
            runtime_revision="a" * 40,
            source_verification_relative="README.md",
        )
        evaluator_role = _evaluator_role(
            root=self.root,
            output="data/evidence/formal/test/erpnext",
            check_ids=("check-a", "check-b"),
        )
        self.assertEqual(
            tool_role["primary_payload"]["tool_count"],
            17,
        )
        self.assertEqual(
            len(evaluator_role["primary_payload"]["checks"]),
            2,
        )
        self.assertIn(
            "rq_jobs",
            evaluator_role["primary_payload"]["scored_state_fields"],
        )

    def test_reference_rejects_state_tampering_even_if_report_is_unchanged(
        self,
    ) -> None:
        payload = self._formal_reference()
        tampered = copy.deepcopy(payload)
        tampered["final_evidence"]["pickup_delivery"] = None
        with self.assertRaises(ERPNextFormalBuildSpecError):
            _validate_reference(
                tampered,
                prefix=self.prefix,
                scenario=self.scenario,
                variant_id="request_not_reached",
            )


if __name__ == "__main__":
    unittest.main()
