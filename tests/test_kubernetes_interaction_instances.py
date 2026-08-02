from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_instance import (
    DEFAULT_KUBERNETES_INTERACTION_INSTANCE,
    KubernetesInteractionInstanceSpec,
    kubernetes_interaction_blueprint,
)
from scripts.verify_kubernetes_interaction_instance_novelty import (
    MINIMUM_SEMANTIC_FACT_CHANGES,
    find_identity_overlaps,
    semantic_change_report,
    validate_bound_blueprint,
    validate_reuse_seal,
)


class KubernetesInteractionInstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.spec_path = (
            cls.root / "data" / "instance_specs" / "public-dev-slot-003.json"
        )
        cls.blueprint_path = (
            cls.root
            / "data"
            / "scenario_blueprints"
            / "public-dev-slot-003"
            / "scenario.json"
        )

    def test_default_instance_preserves_the_consumed_fixture(self) -> None:
        instance = DEFAULT_KUBERNETES_INTERACTION_INSTANCE
        instance.validate()
        self.assertEqual(instance.target_change_id, "orders-platform-v2")
        self.assertEqual(instance.registry_prepare_key, "prepare:orders-platform-v2")
        self.assertEqual(instance.contract_configmaps[0], "schema-contract")

    def test_public_instance_changes_identity_and_semantic_facts(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec_path)
        report = semantic_change_report(instance)
        self.assertTrue(report["passed"])
        self.assertGreaterEqual(
            report["changed_field_count"], MINIMUM_SEMANTIC_FACT_CHANGES
        )
        self.assertNotEqual(
            instance.namespace,
            DEFAULT_KUBERNETES_INTERACTION_INSTANCE.namespace,
        )
        self.assertNotEqual(
            instance.target_epoch,
            DEFAULT_KUBERNETES_INTERACTION_INSTANCE.target_epoch,
        )

    def test_checked_blueprint_is_exactly_rendered_from_instance(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec_path)
        expected = kubernetes_interaction_blueprint(
            instance,
            instance_id="dev-006",
            benchmark_split="public_dev",
            hidden_test_eligible=False,
        )
        observed = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
        self.assertEqual(observed, expected)
        self.assertEqual(observed["instance_spec_sha256"], instance.sha256)
        self.assertEqual(len(observed["matched_variants"]), 13)

    def test_renaming_only_does_not_satisfy_semantic_novelty(self) -> None:
        renamed = replace(
            DEFAULT_KUBERNETES_INTERACTION_INSTANCE,
            scenario_id="renamed-scenario",
            namespace="renamed-namespace",
            application="renamed-app",
            change_stem="renamed-change",
        )
        renamed.validate()
        report = semantic_change_report(renamed)
        self.assertFalse(report["passed"])
        self.assertEqual(report["changed_field_count"], 0)

    def test_identity_overlap_reports_the_field_and_path(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec_path)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "consumed.txt"
            path.write_text(
                f"previous namespace={instance.namespace}\n",
                encoding="utf-8",
            )
            overlaps = find_identity_overlaps(instance, [path])
        self.assertIn("namespace", {item["field"] for item in overlaps})

    def test_bound_blueprint_must_bind_the_instance_hash(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec_path)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "scenario.json"
            path.write_text(
                json.dumps(
                    {
                        "scenario_id": instance.scenario_id,
                        "instance_spec_sha256": "0" * 64,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "sha256"):
                validate_bound_blueprint(instance, path)

    def test_reuse_seal_replays_the_initial_novelty_proof(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec_path)
        seal = (
            self.root
            / "data"
            / "admission_seals"
            / "kubernetes-public-dev-slot-003-initial-novelty.json"
        )
        proof = validate_reuse_seal(
            seal,
            root=self.root,
            instance=instance,
            instance_spec_path=self.spec_path,
            bound_blueprint_path=self.blueprint_path,
        )
        self.assertEqual(
            proof["source_commit"],
            "8a967fcdc5ebd224b367cbb98768e1af00a6b222",
        )
        self.assertEqual(
            proof["historical_scanned_candidate_file_count"],
            0,
        )
        self.assertEqual(
            proof["derived_evidence_roots"],
            ["data/diagnostics/kubernetes/k4-30741680378"],
        )

    def test_reuse_seal_cannot_hide_the_entire_diagnostic_tree(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec_path)
        source = (
            self.root
            / "data"
            / "admission_seals"
            / "kubernetes-public-dev-slot-003-initial-novelty.json"
        )
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["derived_evidence_roots"] = [
            "data/diagnostics/kubernetes"
        ]
        with tempfile.TemporaryDirectory() as raw:
            seal = Path(raw) / "seal.json"
            seal.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "specific descendants"):
                validate_reuse_seal(
                    seal,
                    root=self.root,
                    instance=instance,
                    instance_spec_path=self.spec_path,
                    bound_blueprint_path=self.blueprint_path,
                )

    def test_public_instance_drives_runtime_manifests_and_gold(self) -> None:
        instance = KubernetesInteractionInstanceSpec.from_path(self.spec_path)
        source = """
import json
from aftermath_bench.integrations import kubernetes_interaction_prefix as p
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    INTERACTION_VARIANT_FACTS,
)
from aftermath_bench.native_kubernetes_interaction_family import _control_target

manifests = p.interaction_prefix_manifests()
print(json.dumps({
    "scenario_id": p.SCENARIO_ID,
    "namespace": p.NAMESPACE,
    "application": p.APPLICATION,
    "change_id": p.CHANGE_ID,
    "versions": [p.CURRENT_VERSION, p.TARGET_VERSION],
    "epochs": [p.CURRENT_EPOCH, p.TARGET_EPOCH],
    "generations": [
        p.CURRENT_CREDENTIAL_GENERATION,
        p.TARGET_CREDENTIAL_GENERATION,
    ],
    "manifest_text": json.dumps(manifests, sort_keys=True),
    "state_13": INTERACTION_VARIANT_FACTS["state_13"],
    "control": _control_target("state_13"),
}, sort_keys=True))
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(self.root / "src")
        environment[
            "AFTERMATH_KUBERNETES_INTERACTION_INSTANCE_SPEC"
        ] = str(self.spec_path)
        completed = subprocess.run(
            [sys.executable, "-c", source],
            cwd=self.root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(
            payload["scenario_id"],
            instance.scenario_id,
        )
        self.assertEqual(payload["namespace"], instance.namespace)
        self.assertEqual(payload["application"], instance.application)
        self.assertEqual(
            payload["versions"],
            [instance.current_version, instance.target_version],
        )
        self.assertEqual(
            payload["epochs"],
            [instance.current_epoch, instance.target_epoch],
        )
        self.assertEqual(
            payload["generations"],
            [
                instance.current_credential_generation,
                instance.target_credential_generation,
            ],
        )
        self.assertEqual(
            payload["state_13"]["schema_epoch"], instance.target_epoch
        )
        self.assertEqual(
            payload["state_13"]["credential_generation"],
            instance.current_credential_generation,
        )
        self.assertIn(instance.target_change_id, payload["manifest_text"])
        self.assertNotIn(
            DEFAULT_KUBERNETES_INTERACTION_INSTANCE.target_change_id,
            payload["manifest_text"],
        )
        self.assertEqual(
            payload["control"]["terminal_state"][
                "shared_credential_generation"
            ],
            instance.target_credential_generation,
        )


if __name__ == "__main__":
    unittest.main()
