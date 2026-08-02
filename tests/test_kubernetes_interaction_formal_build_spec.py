from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_instance import (
    KubernetesInteractionInstanceSpec,
)
from aftermath_bench.kubernetes_interaction_formal_build_spec import (
    KubernetesInteractionFormalBuildSpecError,
    _evaluator_role,
    _instance_spec_sha256,
    _tool_role,
    _validate_reference,
)
from aftermath_bench.native_scenario import load_native_scenario


class KubernetesInteractionFormalBuildSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.scenario = load_native_scenario(
            cls.root
            / "data"
            / "scenarios"
            / "k8s-constraint-interactions-dev-005"
            / "scenario.json"
        )
        cls.reference_path = (
            cls.root
            / "data"
            / "evidence"
            / "kubernetes-constraint-interaction-admission-final-20260730"
            / "runtime"
            / "state_01-reference.json"
        )

    def _reference(self) -> dict:
        return json.loads(self.reference_path.read_text(encoding="utf-8"))

    def test_reference_is_recomputed_from_native_terminal_evidence(self) -> None:
        checks = _validate_reference(
            self._reference(),
            scenario=self.scenario,
            variant_id="state_01",
        )
        self.assertEqual(len(checks), 31)
        self.assertIn("boundary_effect_envelope_respected", checks)

    def test_reference_rejects_forged_evaluator_result(self) -> None:
        payload = copy.deepcopy(self._reference())
        payload["evaluation"]["checks"]["no_protocol_violation"] = False
        with self.assertRaises(KubernetesInteractionFormalBuildSpecError):
            _validate_reference(
                payload,
                scenario=self.scenario,
                variant_id="state_01",
            )

    def test_roles_cover_the_public_tools_and_scored_state(self) -> None:
        tool = _tool_role(
            root=self.root,
            output="data/evidence/formal/test/kubernetes",
            runtime_revision="a" * 40,
            source_verification_relative=(
                "data/evidence/kubernetes-native-reset-20260729/"
                "kubernetes-source-verification.json"
            ),
        )
        evaluator = _evaluator_role(
            root=self.root,
            output="data/evidence/formal/test/kubernetes",
            check_ids=("check-a", "check-b"),
        )
        self.assertEqual(tool["primary_payload"]["tool_count"], 13)
        self.assertEqual(
            {item["name"] for item in tool["primary_payload"]["tools"]},
            {
                "get_object",
                "list_objects",
                "list_events",
                "get_job_logs",
                "create_object",
                "apply_object",
                "patch_object",
                "delete_object",
                "wait_for_job",
                "wait_for_deployment",
                "list_external_deliveries",
                "get_external_delivery",
                "post_external_event",
            },
        )
        self.assertIn(
            "boundary_facts",
            evaluator["primary_payload"]["scored_state_fields"],
        )

    def test_instance_binding_uses_canonical_json_not_file_bytes(self) -> None:
        source = (
            self.root
            / "data"
            / "instance_specs"
            / "public-dev-slot-003.json"
        )
        instance = KubernetesInteractionInstanceSpec.from_path(source)
        payload = json.loads(source.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            reformatted = Path(temporary) / "instance.json"
            reformatted.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            self.assertNotEqual(source.read_bytes(), reformatted.read_bytes())
            self.assertEqual(_instance_spec_sha256(source), instance.sha256)
            self.assertEqual(_instance_spec_sha256(reformatted), instance.sha256)


if __name__ == "__main__":
    unittest.main()
