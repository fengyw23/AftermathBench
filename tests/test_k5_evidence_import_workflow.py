from __future__ import annotations

import unittest
from pathlib import Path


class KubernetesK5EvidenceImportWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.path = (
            cls.root
            / ".github"
            / "workflows"
            / "kubernetes-k5-evidence-import.yml"
        )
        cls.workflow = cls.path.read_text(encoding="utf-8")

    def test_import_is_inert_until_reviewed_gate_changes(self) -> None:
        trigger = self.workflow.split("permissions:", maxsplit=1)[0]
        self.assertIn(
            '"data/control_gates/kubernetes-public-dev-slot-003-k5-import.json"',
            trigger,
        )
        self.assertNotIn("workflow_dispatch", trigger)
        self.assertNotIn("schedule:", trigger)

    def test_no_provider_secret_is_available(self) -> None:
        lowered = self.workflow.lower()
        self.assertNotIn("bailian_api_key", lowered)
        self.assertNotIn("aftermath_api_key", lowered)
        self.assertNotIn("secrets.", lowered)
        self.assertIn("actions: read", self.workflow)
        self.assertIn("contents: write", self.workflow)

    def test_exact_successful_k4_run_and_artifact_are_required(self) -> None:
        self.assertIn('and .status == "completed"', self.workflow)
        self.assertIn('and .conclusion == "success"', self.workflow)
        self.assertIn(
            'and .path == ".github/workflows/'
            'kubernetes-interaction-execution-control.yml"',
            self.workflow,
        )
        self.assertIn(".head_sha == $commit", self.workflow)
        self.assertIn("kubernetes-execution-control-", self.workflow)
        self.assertIn(".expired == false", self.workflow)
        self.assertIn("length == 1", self.workflow)

    def test_artifact_roots_and_symlinks_are_rejected_by_default(self) -> None:
        self.assertIn('allowed = {"generated", "scenarios", "evidence"}', self.workflow)
        self.assertIn("observed != allowed", self.workflow)
        self.assertIn("path.is_symlink()", self.workflow)
        safety_calls = [
            block
            for block in self.workflow.split("verify_public_evidence_safe.py")[1:]
        ]
        self.assertGreaterEqual(len(safety_calls), 2)
        self.assertNotIn("--allow-native-restore-archives", self.workflow)

    def test_scientific_gate_binds_source_model_cases_and_threshold(self) -> None:
        for expected in (
            'summary.get("source_run_id") == gate["source_run_id"]',
            'summary.get("source_commit") == gate["source_commit"]',
            'summary.get("model") == "glm-5.2"',
            'summary.get("expected_cases") == 13',
            'summary.get("completed_runs") == 13',
            'summary.get("run_error_count") == 0',
            '== 13',
        ):
            self.assertIn(expected, self.workflow)
        self.assertIn('float(gate["minimum_pass_rate"])', self.workflow)

    def test_import_derives_but_does_not_bind_release_candidate(self) -> None:
        self.assertIn("generate_formal_release_binding.py", self.workflow)
        self.assertIn("k5-release-binding-candidate.json", self.workflow)
        self.assertNotIn("data/release_manifest.json", self.workflow)
        self.assertIn("validate-native-scenario", self.workflow)

    def test_commit_allowlist_contains_only_three_public_evidence_roots(self) -> None:
        section = self.workflow.split(
            "- name: Commit only reviewed K5 evidence", maxsplit=1
        )[1]
        self.assertIn('git add -- "$GENERATED_ROOT" "$SCENARIO_ROOT" "$FORMAL_ROOT"', section)
        self.assertIn("unexpected file outside K5 import allowlist", section)
        self.assertIn('git push origin "HEAD:${GITHUB_REF_NAME}"', section)


if __name__ == "__main__":
    unittest.main()
