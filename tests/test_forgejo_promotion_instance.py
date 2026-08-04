from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
    promotion_blueprint,
)
from aftermath_bench.integrations.forgejo_promotion_prefix import (
    ForgejoPromotionPrefixBuilder,
    promotion_workflow,
)
from aftermath_bench.schema import repository_root


class ForgejoPromotionInstanceTest(unittest.TestCase):
    def setUp(self) -> None:
        root = repository_root()
        self.spec_path = (
            root
            / "data"
            / "instance_specs"
            / "forgejo-approved-artifact-promotion-public-dev-001.json"
        )
        self.blueprint_path = (
            root
            / "data"
            / "scenario_blueprints"
            / "forgejo-approved-artifact-promotion-public-dev-001"
            / "scenario.json"
        )

    def test_checked_blueprint_is_renderer_output(self) -> None:
        instance = ForgejoPromotionInstanceSpec.from_path(self.spec_path)
        checked = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
        self.assertEqual(checked, promotion_blueprint(instance))
        self.assertEqual(checked["instance_spec_sha256"], instance.sha256)
        self.assertEqual(len(checked["matched_variants"]), 6)
        self.assertEqual(len(checked["required_public_evidence"]), 8)

    def test_family_crosses_approval_artifact_deployment_and_publication(self) -> None:
        checked = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
        evidence = " ".join(checked["required_public_evidence"])
        for required in ("approval", "artifact", "deployment", "attestation", "prior"):
            self.assertIn(required, evidence)
        signatures = {
            row["recovery_signature_class"] for row in checked["matched_variants"]
        }
        self.assertEqual(len(signatures), 6)

    def test_rejects_unsafe_or_nonindependent_instance(self) -> None:
        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload["binary_path"] = "../outside.tar.gz"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsafe repository path"):
                ForgejoPromotionInstanceSpec.from_path(path)

        payload = json.loads(self.spec_path.read_text(encoding="utf-8"))
        payload["release_tag"] = payload["protected_release_tag"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "release tags must differ"):
                ForgejoPromotionInstanceSpec.from_path(path)

    def test_native_workflow_materializes_all_recovery_systems(self) -> None:
        instance = ForgejoPromotionInstanceSpec.from_path(self.spec_path)
        workflow = promotion_workflow(instance)
        self.assertIn("runs-on: aftermath-native", workflow)
        self.assertIn(
            "https://data.forgejo.org/actions/upload-artifact@v3", workflow
        )
        self.assertIn("/artifacts", workflow)
        self.assertIn("/artifact-deployments", workflow)
        self.assertIn("/workers/run", workflow)
        self.assertIn("/webhooks/events", workflow)
        self.assertIn("resume_stage", workflow)
        self.assertIn("stop_after", workflow)

    def test_prefix_uses_public_apis_and_preserves_three_records(self) -> None:
        instance = ForgejoPromotionInstanceSpec.from_path(self.spec_path)
        forgejo = MagicMock()
        forgejo.create_repository.return_value = {
            "id": 1,
            "owner": {"login": instance.owner},
        }
        forgejo.edit_repository.return_value = {"has_releases": True}
        forgejo.create_issue.side_effect = [
            {"number": 1},
            {"number": 2},
            {"number": 3},
        ]
        forgejo.edit_issue.return_value = {"number": 1, "state": "closed"}
        forgejo.create_file.side_effect = [
            {"commit": {"sha": f"commit-{index}"}} for index in range(1, 7)
        ]
        forgejo.create_release.return_value = {
            "tag_name": instance.protected_release_tag
        }
        deployment = MagicMock()
        deployment.register_artifact.return_value = {"first_registration": True}
        deployment.request_artifact_deployment.return_value = {"created": True}
        deployment.run_workers.return_value = {"completed_job_ids": [1]}
        deployment.state.return_value = {"deployments": []}
        prefix = ForgejoPromotionPrefixBuilder(
            forgejo, deployment, instance
        ).build()
        self.assertEqual(prefix.repository_head, "commit-6")
        self.assertEqual(prefix.approval_issue_index, 1)
        self.assertEqual(prefix.rollout_issue_index, 2)
        self.assertEqual(prefix.unrelated_issue_index, 3)
        self.assertEqual(
            {event["system"] for event in prefix.trace},
            {"forgejo", "deployment-target"},
        )


if __name__ == "__main__":
    unittest.main()
