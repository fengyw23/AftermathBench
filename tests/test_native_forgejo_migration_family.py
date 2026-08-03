from __future__ import annotations

import json
import unittest

from aftermath_bench.native_forgejo_migration_family import (
    FORGEJO_MIGRATION_FAMILY,
    FORGEJO_MIGRATION_TOOL_DEFINITIONS,
    evaluate_forgejo_migration_model_state,
    forgejo_migration_initial_message,
)
from aftermath_bench.native_model_runner import (
    NATIVE_FAMILY_REGISTRY,
    validate_native_run_bindings,
)
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeForgejoMigrationFamilyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = repository_root()
        cls.scenario = load_native_scenario(
            cls.root
            / "data"
            / "scenarios"
            / "forgejo-migration-deployment-dev-002"
            / "scenario.json"
        )
        cls.prefix = json.loads(
            (
                cls.root
                / "data"
                / "scenarios"
                / "forgejo-migration-deployment-dev-002"
                / "artifacts"
                / "prefix.json"
            ).read_text(encoding="utf-8")
        )

    def test_family_is_registered_with_ordinary_tools(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("forgejo-migration-deployment"),
            FORGEJO_MIGRATION_FAMILY,
        )
        names = {tool.name for tool in FORGEJO_MIGRATION_TOOL_DEFINITIONS}
        self.assertIn("list_action_runs", names)
        self.assertIn("get_deployment_state", names)
        self.assertIn("dispatch_workflow", names)
        self.assertIn("start_action_runner", names)
        self.assertNotIn("repair_deployment", names)
        self.assertNotIn("get_recommended_action", names)
        for tool in FORGEJO_MIGRATION_TOOL_DEFINITIONS:
            self.assertFalse(tool.input_schema["additionalProperties"])

    def test_initial_message_exposes_failure_not_hidden_variant(self) -> None:
        failure = {
            "visible_failure": {
                "ok": False,
                "error": "connection closed before workflow dispatch was acknowledged",
            }
        }
        message = forgejo_migration_initial_message(
            scenario=self.scenario,
            prefix=self.prefix,
            failure_report=failure,
        )
        self.assertIn(self.prefix["workflow_path"], message)
        self.assertIn(self.prefix["repository"], message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)

    def test_deterministic_snapshot_evaluation_adapts_to_runner_contract(self) -> None:
        checks = {"goal": True, "preserved": False}
        components = {
            "goal_completion": True,
            "repair_completeness": True,
            "preservation": False,
            "protocol_safety": True,
        }
        evaluation = evaluate_forgejo_migration_model_state(
            {
                "_deterministic_evaluation": {
                    "variant": "dispatch_request_not_reached",
                    "passed": False,
                    "checks": checks,
                    "components": components,
                },
                "action_runs": [{"id": 1}],
                "action_jobs": [{"id": 2}],
            },
            prefix={},
        )
        self.assertFalse(evaluation.passed)
        self.assertEqual(evaluation.failures, ("preserved",))
        self.assertEqual(evaluation.diagnostics["action_run_count"], 1)

    def test_boundary_report_binds_scenario_instance_and_visible_failure(self) -> None:
        text = (self.root / "scripts" / "run_forgejo_migration_boundary.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"scenario_id": instance.scenario_id', text)
        self.assertIn('"instance_spec_sha256": instance.sha256', text)
        self.assertIn('"visible_failure": {', text)

    def test_runner_rejects_an_unbound_migration_failure_report(self) -> None:
        with self.assertRaisesRegex(ValueError, "must all bind"):
            validate_native_run_bindings(
                scenario=self.scenario,
                prefix=self.prefix,
                failure_report={
                    "scenario_id": self.scenario.scenario_id,
                    "variant": self.scenario.variants[0],
                    "visible_failure": {"ok": False},
                },
                family_id="forgejo-migration-deployment",
            )


if __name__ == "__main__":
    unittest.main()
