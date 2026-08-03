from __future__ import annotations

import unittest

from aftermath_bench.schema import repository_root


class KubernetesInteractionModelWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = (
            repository_root()
            / ".github"
            / "workflows"
            / "kubernetes-interaction-model.yml"
        ).read_text(encoding="utf-8")

    def test_uses_bailian_secret_and_compatible_endpoint(self) -> None:
        self.assertIn("secrets.BAILIAN_API_KEY", self.text)
        self.assertIn("compatible-mode/v1", self.text)
        self.assertNotIn("sk-", self.text)

    def test_checkout_contains_history_required_by_reuse_seal(self) -> None:
        checkout = self.text.index("uses: actions/checkout@v4")
        setup = self.text.index("uses: actions/setup-python@v5", checkout)
        self.assertIn("fetch-depth: 0", self.text[checkout:setup])

    def test_rebuilds_every_boundary_before_each_provider_attempt(self) -> None:
        boundary = self.text.index("run_kubernetes_interaction_boundary.py")
        model = self.text.index("run-native-model", boundary)
        retry_loop = self.text.index("for attempt in 1 2 3")
        self.assertLess(retry_loop, boundary)
        self.assertLess(boundary, model)

    def test_provider_timeout_override_is_bounded_and_non_semantic(self) -> None:
        self.assertIn("model_timeout_seconds:", self.text)
        self.assertIn("600|1200|1800", self.text)
        self.assertIn(
            '--model-timeout-seconds "$MODEL_TIMEOUT_SECONDS"',
            self.text,
        )
        self.assertIn("model_stream:", self.text)
        self.assertIn("stream_flag=(--model-stream)", self.text)

    def test_control_and_ordinary_conditions_have_distinct_push_branches(self) -> None:
        self.assertIn("interaction-model-control", self.text)
        self.assertIn("interaction-model-eval", self.text)
        self.assertIn("--expected-execution-control", self.text)

    def test_full_control_run_enforces_the_scientific_gate(self) -> None:
        self.assertIn('CONTROL_MIN_PASS_RATE: "0.8"', self.text)
        self.assertIn(
            'if [ "$EXECUTION_CONTROL" = "true" ] && '
            '[ -z "$VARIANT_SUBSET" ]',
            self.text,
        )
        self.assertIn('summary["task_pass_rate"]', self.text)
        self.assertIn("observed < threshold", self.text)

    def test_all_thirteen_neutral_variants_are_declared(self) -> None:
        for index in range(1, 14):
            self.assertIn(f"state_{index:02d}", self.text)

    def test_model_uses_the_native_admitted_scenario(self) -> None:
        self.assertIn(
            "data/scenarios/k8s-constraint-interactions-dev-005/scenario.json",
            self.text,
        )
        self.assertNotIn(
            "data/scenario_blueprints/k8s-constraint-interactions-dev-005/scenario.json",
            self.text,
        )


if __name__ == "__main__":
    unittest.main()
