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
        candidates = list(
            (repository_root() / "data" / "instance_specs").glob(
                "forgejo-package-provenance-public-*.json"
            )
        )
        if len(candidates) != 1:
            raise AssertionError(candidates)
        cls.path = candidates[0]
        cls.instance = ForgejoPublicationInstanceSpec.from_path(cls.path)

    def test_fresh_public_instance_is_valid_and_not_template_bound(self) -> None:
        self.assertTrue(self.instance.owner)
        self.assertTrue(self.instance.version)
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
        self.assertEqual(
            blueprint["fixture"]["package_name"], self.instance.package_slug
        )
        profile = blueprint["admission_profile"]["adaptive_recovery"]
        self.assertEqual(profile["minimum_adaptive_query_depth"], 3)
        self.assertEqual(profile["minimum_variant_specific_mutations"], 2)
        self.assertEqual(profile["minimum_pairwise_mutation_distance"], 2)
        serialized = str(blueprint)
        self.assertIn(self.instance.version, serialized)
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

    def test_r2_blueprint_requires_non_monotonic_same_inventory_pair(self) -> None:
        r2_instance = ForgejoPublicationInstanceSpec.from_path(
            repository_root()
            / "data"
            / "instance_specs"
            / "forgejo-package-provenance-nonmonotonic-dev-001.json"
        )
        blueprint = package_provenance_blueprint(
            r2_instance,
            instance_id="dev-r2-001",
            benchmark_split="development",
            hidden_test_eligible=False,
            generation="r2",
        )
        variants = {item["id"]: item for item in blueprint["matched_variants"]}
        self.assertIn("r2_package_complete_index_missing", variants)
        self.assertIn("r2_package_corrupt_binary_index_missing", variants)
        profile = blueprint["admission_profile"]["adaptive_recovery"]
        self.assertTrue(profile["requires_same_inventory_opposite_scope_pair"])
        self.assertTrue(profile["requires_non_monotonic_repair"])
        self.assertEqual(profile["minimum_adaptive_query_depth"], 4)
        persisted = json.loads(
            (
                repository_root()
                / "data"
                / "scenario_blueprints"
                / r2_instance.scenario_id
                / "scenario.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(persisted, blueprint)

    def test_runtime_creates_the_owner_declared_by_selected_instance(self) -> None:
        workflow = (
            repository_root()
            / ".github"
            / "workflows"
            / "forgejo-package-provenance-runtime.yml"
        ).read_text(encoding="utf-8")
        prefix = workflow[
            workflow.index("Build and freeze the package prefix") :
            workflow.index("Replay matched boundaries")
        ]
        self.assertIn('json.load(open(sys.argv[1]', prefix)
        self.assertIn('["owner"]', prefix)
        self.assertIn('--username "$owner"', prefix)


if __name__ == "__main__":
    unittest.main()
