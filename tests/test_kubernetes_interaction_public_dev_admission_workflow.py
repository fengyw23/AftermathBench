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
        self.assertIn("Replay 117 fixed policies from byte-locked", self.workflow)
        self.assertIn("verify_kubernetes_interaction_public_dev_admission.py", self.workflow)
        lowered = self.workflow.lower()
        self.assertNotIn("api_key", lowered)
        self.assertNotIn("secrets.", lowered)
        self.assertNotIn("run-native-model", lowered)

    def test_freezes_all_five_formal_inputs_before_any_model_work(self) -> None:
        self.assertIn(
            "Freeze the five formal input roles without provider access",
            self.workflow,
        )
        self.assertIn(
            "generate_kubernetes_interaction_formal_build_spec.py",
            self.workflow,
        )
        self.assertIn("--phase inputs", self.workflow)
        self.assertIn("build_formal_evidence.py", self.workflow)
        self.assertIn("formal-input-lock.json", self.workflow)
        self.assertNotIn("secrets.", self.workflow.lower())

    def test_formal_inputs_use_one_reset_and_thirteen_exact_boundary_bundles(
        self,
    ) -> None:
        exact = self.workflow.index(
            "Replay thirteen exact native boundaries and references"
        )
        baseline = self.workflow.index("Replay 117 fixed policies", exact)
        section = self.workflow[exact:baseline]
        prepare = section.index("--prepare-only")
        reset_snapshot = section.index("snapshot-bundle", prepare)
        reset_bundle = section.index('"$sensitive_root/prefix"', reset_snapshot)
        restore = section.index("restore-bundle", reset_bundle)
        restored_bundle = section.index('"$sensitive_root/prefix"', restore)
        trigger = section.index("--trigger-only", restore)
        boundary_snapshot = section.index("snapshot-bundle", trigger)
        boundary_restore = section.index("restore-bundle", boundary_snapshot)
        pre_snapshot = section.index("--pre-snapshot-state", boundary_restore)
        reference_restore = section.index("restore-bundle", pre_snapshot)
        expected = section.index('--expected "$boundary"', reference_restore)
        self.assertLess(prepare, reset_snapshot)
        self.assertLess(reset_snapshot, reset_bundle)
        self.assertLess(reset_bundle, restore)
        self.assertLess(restore, restored_bundle)
        self.assertLess(restore, trigger)
        self.assertLess(trigger, boundary_snapshot)
        self.assertLess(boundary_snapshot, boundary_restore)
        self.assertLess(boundary_restore, pre_snapshot)
        self.assertLess(pre_snapshot, reference_restore)
        self.assertLess(reference_restore, expected)

    def test_references_restore_and_fixed_policies_byte_lock_boundaries(
        self,
    ) -> None:
        self.assertIn("Install checksum-pinned etcdutl", self.workflow)
        self.assertIn("prepare-snapshot-runtime", self.workflow)
        self.assertIn("snapshot-bundle", self.workflow)
        self.assertIn("restore-bundle", self.workflow)
        self.assertIn("--expected", self.workflow)
        self.assertIn("--wait-seconds 180", self.workflow)
        baseline_step = self.workflow.index(
            "Replay 117 fixed policies from byte-locked native boundaries"
        )
        admission_step = self.workflow.index(
            "Build and verify replay-derived hard admission"
        )
        baseline_text = self.workflow[baseline_step:admission_step]
        self.assertNotIn("restore-bundle", baseline_text)
        self.assertIn("run_kubernetes_interaction_boundary.py", baseline_text)
        self.assertIn("--expected", baseline_text)
        self.assertIn(
            '"src/aftermath_bench/integrations/kubernetes_stack.py"',
            self.workflow,
        )

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
