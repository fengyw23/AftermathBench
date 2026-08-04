from __future__ import annotations

import json
import unittest
from pathlib import Path


class ForgejoMigrationPublicDevCandidateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/forgejo-migration-public-dev-candidate.yml"
        ).read_text(encoding="utf-8")
        cls.scenario_id = json.loads(
            Path(
                "data/instance_specs/forgejo-migration-public-dev-001.json"
            ).read_text(encoding="utf-8")
        )["scenario_id"]

    def test_novelty_and_rendering_precede_native_runtime(self) -> None:
        novelty = self.text.index(
            "verify_forgejo_migration_instance_novelty.py"
        )
        render = self.text.index("render_forgejo_migration_blueprint.py")
        build = self.text.index("build_forgejo_runtime.py")
        self.assertLess(novelty, render)
        self.assertLess(render, build)
        self.assertIn("fetch-depth: 0", self.text)
        self.assertNotIn(
            self.scenario_id,
            self.text,
        )

    def test_boundaries_are_captured_replayed_and_admitted(self) -> None:
        replay = self.text[
            self.text.index("Replay four exact boundaries"):
            self.text.index("Execute fixed policies")
        ]
        self.assertEqual(
            replay.count("capture_forgejo_migration_state_evidence.py"),
            3,
        )
        self.assertIn(
            "verify_forgejo_migration_boundary_replay.py",
            replay,
        )
        self.assertIn("run_forgejo_migration_reference.py", replay)
        self.assertIn("--runner-disabled", replay)
        self.assertIn("build_forgejo_migration_admission.py", self.text)
        self.assertIn("validate-native-scenario", self.text)

    def test_candidate_is_not_misrepresented_as_formal_evidence(self) -> None:
        self.assertNotIn("build_formal_evidence.py", self.text)
        self.assertNotIn("formal-release-binding", self.text)
        self.assertNotIn("run-native-model", self.text)
        self.assertIn("verify_public_evidence_safe.py", self.text)
        self.assertIn("--allow-native-restore-archives", self.text)
        self.assertIn("$RUN_ROOT/scenario-staging", self.text)
        self.assertNotIn('test ! -e "data/scenarios/$scenario_id"', self.text)
        staging = self.text.index("$RUN_ROOT/scenario-staging")
        manifest = self.text.index("build_evidence_file_manifest.py")
        self.assertLess(staging, manifest)


if __name__ == "__main__":
    unittest.main()
