from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_instance import (
    DEFAULT_KUBERNETES_INTERACTION_INSTANCE,
    KubernetesInteractionInstanceSpec,
)


class KubernetesInteractionPublicDevAdmissionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.spec = (
            cls.root / "data" / "instance_specs" / "public-dev-slot-003.json"
        )
        cls.workflow = (
            cls.root
            / ".github"
            / "workflows"
            / "kubernetes-interaction-public-dev-admission.yml"
        ).read_text(encoding="utf-8")

    def test_workflow_runs_complete_fixed_matrix_without_provider(self) -> None:
        self.assertIn("Replay thirteen exact native boundaries", self.workflow)
        self.assertIn("Replay 117 fixed policies from exact", self.workflow)
        self.assertIn("verify_kubernetes_interaction_public_dev_admission.py", self.workflow)
        lowered = self.workflow.lower()
        self.assertNotIn("api_key", lowered)
        self.assertNotIn("secrets.", lowered)
        self.assertNotIn("run-native-model", lowered)

    def test_every_consumer_restores_one_uid_preserving_boundary(self) -> None:
        self.assertIn("Install checksum-pinned etcdutl", self.workflow)
        self.assertIn("prepare-snapshot-runtime", self.workflow)
        self.assertIn("snapshot-bundle", self.workflow)
        self.assertIn("restore-bundle", self.workflow)
        self.assertIn("--expected", self.workflow)
        self.assertIn("--wait-seconds 180", self.workflow)
        baseline_step = self.workflow.index(
            "Replay 117 fixed policies from exact native boundaries"
        )
        admission_step = self.workflow.index(
            "Build and verify replay-derived hard admission"
        )
        baseline_text = self.workflow[baseline_step:admission_step]
        self.assertIn("restore-bundle", baseline_text)
        self.assertNotIn("run_kubernetes_interaction_boundary.py", baseline_text)

    def test_admission_builder_uses_public_blueprint_explicitly(self) -> None:
        self.assertIn("--blueprint", self.workflow)
        self.assertIn(
            "data/scenario_blueprints/public-dev-slot-003/scenario.json",
            self.workflow,
        )

    def test_historical_regressions_run_without_active_instance_override(
        self,
    ) -> None:
        novelty = self.workflow.index(
            "verify_kubernetes_interaction_instance_novelty.py"
        )
        unset = self.workflow.index(
            "unset AFTERMATH_KUBERNETES_INTERACTION_INSTANCE_SPEC"
        )
        tests = self.workflow.index("python -m unittest discover", unset)
        runtime = self.workflow.index(
            "Replay thirteen exact native boundaries and references"
        )
        self.assertLess(novelty, unset)
        self.assertLess(unset, tests)
        self.assertLess(tests, runtime)

    def test_public_graph_selectors_follow_instance_contract_names(self) -> None:
        source = """
import importlib.util
import json
from pathlib import Path

path = Path('scripts/build_kubernetes_interaction_admission.py')
spec = importlib.util.spec_from_file_location('builder', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(module._observed_graph(), sort_keys=True))
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(self.root / "src")
        environment[
            "AFTERMATH_KUBERNETES_INTERACTION_INSTANCE_SPEC"
        ] = str(self.spec)
        completed = subprocess.run(
            [sys.executable, "-c", source],
            cwd=self.root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        rendered = completed.stdout
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec)
        self.assertIn(instance.schema_contract, rendered)
        self.assertIn(instance.audit_contract, rendered)
        self.assertNotIn(
            f'"contracts.{DEFAULT_KUBERNETES_INTERACTION_INSTANCE.schema_contract}"',
            rendered,
        )


if __name__ == "__main__":
    unittest.main()
