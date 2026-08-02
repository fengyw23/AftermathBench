from __future__ import annotations

import json
import unittest
from pathlib import Path


class KubernetesK4ExecutionControlWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.path = (
            cls.root
            / ".github"
            / "workflows"
            / "kubernetes-interaction-execution-control.yml"
        )
        cls.workflow = cls.path.read_text(encoding="utf-8")

    def test_workflow_is_inert_until_reviewed_gate_file_changes(self) -> None:
        trigger = self.workflow.split("permissions:", maxsplit=1)[0]
        self.assertIn(
            '"data/control_gates/kubernetes-public-dev-slot-003-k4.json"',
            trigger,
        )
        self.assertNotIn(
            "kubernetes-interaction-execution-control.yml",
            trigger,
        )
        self.assertNotIn("workflow_dispatch", trigger)

    def test_execution_uses_the_exact_input_producer_and_source_artifacts(
        self,
    ) -> None:
        self.assertIn(
            'SOURCE_COMMIT: "ddd961344ba7390744f509b8d6a76ac97a5c24cc"',
            self.workflow,
        )

    def test_reviewed_gate_matches_the_pinned_source_and_threshold(self) -> None:
        gate = json.loads(
            (
                self.root
                / "data"
                / "control_gates"
                / "kubernetes-public-dev-slot-003-k4.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            gate,
            {
                "schema_version": "1.0",
                "stage": "K4-execution-control",
                "source_run_id": 30745076781,
                "source_commit": (
                    "ddd961344ba7390744f509b8d6a76ac97a5c24cc"
                ),
                "model": "DeepSeek-V4-Pro",
                "minimum_pass_rate": 0.8,
            },
        )
        self.assertIn('SOURCE_RUN_ID: "30745076781"', self.workflow)
        self.assertIn("ref: ${{ env.SOURCE_COMMIT }}", self.workflow)
        self.assertIn(
            "kubernetes-public-dev-admission-30745076781",
            self.workflow,
        )
        self.assertIn(
            "kubernetes-private-replay-30745076781",
            self.workflow,
        )
        self.assertIn(
            ".head_sha == $commit and .status == \"completed\" "
            'and .conclusion == "success"',
            self.workflow,
        )

    def test_provider_secret_is_step_scoped_after_input_verification(self) -> None:
        verify = self.workflow.index(
            "Verify frozen inputs and replay-bundle provenance without provider access"
        )
        provider = self.workflow.index("secrets.PARATERA_API_KEY")
        model = self.workflow.index("run-native-model", provider)
        self.assertLess(verify, provider)
        self.assertLess(provider, model)
        before_provider = self.workflow[:provider].lower()
        self.assertNotIn("paratera_api_key", before_provider)
        self.assertIn("verify_formal_input_lock", self.workflow[verify:provider])
        self.assertIn("verify_public_evidence_safe.py", self.workflow[verify:provider])

    def test_formal_lock_identity_is_loaded_from_the_frozen_scenario(self) -> None:
        self.assertIn("load_native_scenario", self.workflow)
        self.assertIn("scenario_id=scenario.scenario_id", self.workflow)
        self.assertIn("domain_id=scenario.domain_id", self.workflow)
        self.assertIn("family_id=scenario.family_id", self.workflow)
        self.assertIn("instance_id=scenario.instance_id", self.workflow)
        public_scenario_id = "k8s-constraint-interactions-" + "public-dev-006"
        self.assertNotIn(f'scenario_id="{public_scenario_id}"', self.workflow)

    def test_every_control_restores_and_byte_checks_the_frozen_boundary(self) -> None:
        control = self.workflow.index(
            "Run execution controls from exact frozen boundaries"
        )
        complete = self.workflow.index(
            "Complete and validate the seven-role formal package"
        )
        section = self.workflow[control:complete]
        restore = section.index("restore-bundle")
        capture = section.index(
            "capture_kubernetes_interaction_state_evidence.py",
            restore,
        )
        expected = section.index("--expected", capture)
        compare = section.index("cmp", expected)
        model = section.index("run-native-model", compare)
        self.assertLess(restore, capture)
        self.assertLess(capture, expected)
        self.assertLess(expected, compare)
        self.assertLess(compare, model)
        self.assertIn("--formal-input-lock", section)
        self.assertIn("--pre-model-boundary-evidence", section)
        self.assertIn("--execution-control", section)

    def test_control_gate_and_formal_completion_cover_all_thirteen_states(
        self,
    ) -> None:
        self.assertIn("--expected-cases 13", self.workflow)
        self.assertIn('CONTROL_MIN_PASS_RATE: "0.8"', self.workflow)
        self.assertIn("--minimum-pass-rate \"$CONTROL_MIN_PASS_RATE\"", self.workflow)
        self.assertIn("--phase complete", self.workflow)
        self.assertIn("--control-manifest \"$CONTROL_ROOT/files.json\"", self.workflow)
        self.assertIn("completion/declarations.json", self.workflow)
        self.assertIn("control-gate-passed", self.workflow)

    def test_private_restore_material_is_never_uploaded_by_k4(self) -> None:
        upload = self.workflow.index("Upload K4 execution-control evidence")
        purge = self.workflow.index("Purge native services and replay material")
        upload_section = self.workflow[upload:purge]
        self.assertNotIn("kubernetes-private-replay", upload_section)
        self.assertNotIn("kubernetes-k4-registry", upload_section)
        self.assertIn("verify_public_evidence_safe.py", self.workflow)

    def test_k4_publishes_only_aggregate_metrics(self) -> None:
        publish = self.workflow.index(
            "Publish non-sensitive K4 aggregate metrics"
        )
        seal = self.workflow.index(
            "Seal K4 evidence and enforce the control gate"
        )
        section = self.workflow[publish:seal]
        self.assertIn("k4-public-summary.json", section)
        self.assertIn("task_pass_rate", section)
        self.assertIn("component_pass_rates", section)
        self.assertIn("failure_type_counts", section)
        self.assertIn("run_error_count", section)
        self.assertNotIn("reports", section)
        self.assertNotIn("AFTERMATH_API_KEY", section)
        self.assertIn("$GITHUB_STEP_SUMMARY", section)


if __name__ == "__main__":
    unittest.main()
