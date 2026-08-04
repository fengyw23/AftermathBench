from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from aftermath_bench.integrations.forgejo_promotion_instance import (
    ForgejoPromotionInstanceSpec,
)
from aftermath_bench.integrations.forgejo_reconciliation_instance import (
    reconciliation_blueprint,
)
from aftermath_bench.native_forgejo_reconciliation_family import (
    FORGEJO_RECONCILIATION_FAMILY,
    FORGEJO_RECONCILIATION_SYSTEM_PROMPT,
    reconciliation_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.schema import repository_root


class NativeForgejoReconciliationFamilyTest(unittest.TestCase):
    def test_two_checked_blueprints_are_renderer_outputs(self) -> None:
        root = repository_root()
        for instance_id in ("public-dev-001", "public-dev-002"):
            spec = ForgejoPromotionInstanceSpec.from_path(
                root
                / "data"
                / "instance_specs"
                / f"forgejo-approved-artifact-promotion-{instance_id}.json"
            )
            checked = json.loads(
                (
                    root
                    / "data"
                    / "scenario_blueprints"
                    / f"forgejo-cross-system-reconciliation-{instance_id}"
                    / "scenario.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                checked,
                reconciliation_blueprint(spec, instance_id=instance_id),
            )
            self.assertEqual(len(checked["matched_variants"]), 6)
            self.assertEqual(
                checked["planned_admission_profile"]["scope_decision"],
                {
                    "minimum_adaptive_worst_case_depth": 6,
                    "minimum_static_certificate_size": 6,
                },
            )

    def test_family_is_registered_and_exposes_joined_evidence_tools(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get("forgejo-cross-system-reconciliation"),
            FORGEJO_RECONCILIATION_FAMILY,
        )
        names = {tool.name for tool in FORGEJO_RECONCILIATION_FAMILY.tool_definitions}
        for required in (
            "get_repository_content",
            "get_action_artifact_manifest",
            "get_deployment_state",
            "get_external_attestation",
            "list_releases",
            "list_issues",
        ):
            self.assertIn(required, names)
        self.assertNotIn("recommended_repair", names)

    def test_initial_message_does_not_reveal_hidden_gap(self) -> None:
        scenario = SimpleNamespace(raw={"user_instruction": "repair the promotion"})
        prefix = {
            "owner": "aftermath",
            "repository": "service",
            "rollout_issue_index": 2,
            "approval_issue_index": 1,
            "unrelated_issue_index": 3,
            "workflow_path": ".forgejo/workflows/promote.yml",
            "release_tag": "v1.2.3",
            "protected_release_tag": "v1.2.2",
            "repository_head": "native-head",
            "trace": [],
        }
        report = {
            "variant": "external_attestation_missing",
            "surface_result": {"ok": False, "error": "connection closed"},
        }
        message = reconciliation_initial_message(
            scenario=scenario,
            prefix=prefix,
            failure_report=report,
        )
        self.assertNotIn("external_attestation_missing", message)
        self.assertNotIn("repair_attestation_only", message)
        self.assertIn("connection closed", message)

    def test_prompt_requires_investigation_without_answer_tool(self) -> None:
        prompt = FORGEJO_RECONCILIATION_SYSTEM_PROMPT.format(max_turns=30)
        self.assertIn("independently present or missing", prompt)
        self.assertIn("downloaded Actions artifact contents", prompt)
        self.assertNotIn("hidden variant", prompt)


if __name__ == "__main__":
    unittest.main()
