import json
import unittest

from aftermath_bench.integrations.forgejo_package_provenance_instance import (
    package_provenance_blueprint,
)
from aftermath_bench.integrations.forgejo_publication_instance import (
    ForgejoPublicationInstanceSpec,
)
from aftermath_bench.schema import repository_root


class ForgejoPackageProvenanceInstanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = (
            repository_root()
            / "data"
            / "instance_specs"
            / "forgejo-package-provenance-public-dev-001.json"
        )
        cls.instance = ForgejoPublicationInstanceSpec.from_path(cls.path)

    def test_fresh_public_instance_is_valid_and_not_template_bound(self) -> None:
        self.assertEqual(self.instance.owner, "meridian-supply")
        self.assertEqual(self.instance.version, "2.4.1")
        self.assertNotIn("telemetry", self.instance.canonical_json().lower())
        self.assertNotIn("3.7.0", self.instance.canonical_json())

    def test_blueprint_binds_instance_and_strict_reasoning_profile(self) -> None:
        blueprint = package_provenance_blueprint(
            self.instance,
            instance_id="dev-001",
            benchmark_split="public_dev",
            hidden_test_eligible=False,
        )
        self.assertEqual(blueprint["scenario_id"], self.instance.scenario_id)
        self.assertEqual(blueprint["instance_spec_sha256"], self.instance.sha256)
        self.assertEqual(blueprint["fixture"]["package_name"], "orbitctl")
        profile = blueprint["admission_profile"]["adaptive_recovery"]
        self.assertEqual(profile["minimum_adaptive_query_depth"], 3)
        self.assertEqual(profile["minimum_variant_specific_mutations"], 2)
        self.assertEqual(profile["minimum_pairwise_mutation_distance"], 2)
        serialized = str(blueprint)
        self.assertIn("2.4.1", serialized)
        self.assertNotIn("3.7.0", serialized)

        persisted_path = (
            repository_root()
            / "data"
            / "scenario_blueprints"
            / self.instance.scenario_id
            / "scenario.json"
        )
        persisted = json.loads(persisted_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted, blueprint)

    def test_hidden_eligibility_must_match_split(self) -> None:
        with self.assertRaises(ValueError):
            package_provenance_blueprint(
                self.instance,
                instance_id="test-001",
                benchmark_split="public_dev",
                hidden_test_eligible=True,
            )


if __name__ == "__main__":
    unittest.main()
