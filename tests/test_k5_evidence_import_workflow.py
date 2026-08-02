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

    def test_repair_uses_the_same_locked_instance_spec_as_k4(self) -> None:
        self.assertIn(
            "AFTERMATH_KUBERNETES_INTERACTION_INSTANCE_SPEC", self.workflow
        )
        self.assertIn(
            "data/instance_specs/public-dev-slot-003.json", self.workflow
        )

    def test_repair_runs_at_exact_input_producer_with_one_audited_overlay(self) -> None:
        self.assertIn(
            'git worktree add --detach "$repair_root" "$SOURCE_COMMIT"',
            self.workflow,
        )
        self.assertIn(
            'test "$(git rev-parse HEAD)" = "$SOURCE_COMMIT"',
            self.workflow,
        )
        self.assertIn(
            "kubernetes_interaction_formal_build_spec.py", self.workflow
        )

    def test_exact_reviewed_k4_run_and_artifact_are_required(self) -> None:
        self.assertIn("validate_k5_evidence_import.py gate", self.workflow)
        self.assertIn("validate_k5_evidence_import.py provenance", self.workflow)
        self.assertIn('--run-metadata "$RUNNER_TEMP/k4-run.json"', self.workflow)
        self.assertIn(
            '--artifacts-metadata "$RUNNER_TEMP/k4-artifacts.json"',
            self.workflow,
        )
        self.assertIn('gh run download "$K4_RUN_ID"', self.workflow)

    def test_post_model_repair_is_provider_free_and_does_not_rerun_model(self) -> None:
        self.assertIn(
            "effective-default-argument-normalization-v1", self.workflow
        )
        self.assertIn(
            "generate_kubernetes_interaction_formal_build_spec.py",
            self.workflow,
        )
        self.assertIn("build_formal_evidence.py", self.workflow)
        self.assertNotIn("run-native-model", self.workflow)
        self.assertIn("--allow-missing-completion", self.workflow)

    def test_artifact_roots_and_symlinks_are_rejected_by_default(self) -> None:
        self.assertIn("validate_k5_evidence_import.py artifact", self.workflow)
        self.assertIn('--stage "$stage"', self.workflow)
        safety_calls = [
            block
            for block in self.workflow.split("verify_public_evidence_safe.py")[1:]
        ]
        self.assertGreaterEqual(len(safety_calls), 2)
        self.assertNotIn("--allow-native-restore-archives", self.workflow)

    def test_scientific_gate_binds_source_model_cases_and_threshold(self) -> None:
        provenance = self.workflow.index(
            "validate_k5_evidence_import.py provenance"
        )
        download = self.workflow.index("Download the immutable K4 artifact")
        artifact = self.workflow.index("validate_k5_evidence_import.py artifact")
        import_step = self.workflow.index(
            "Import evidence and repair only the post-model formal package"
        )
        self.assertLess(provenance, download)
        self.assertLess(download, artifact)
        self.assertLess(artifact, import_step)

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
