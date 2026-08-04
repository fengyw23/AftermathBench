from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
    promotion_blueprint,
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


if __name__ == "__main__":
    unittest.main()
