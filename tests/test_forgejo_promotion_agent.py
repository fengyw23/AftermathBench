from __future__ import annotations

import io
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock

from aftermath_bench.integrations.forgejo_promotion_agent import (
    ForgejoPromotionEnvironment,
    inspect_action_artifact,
)
from aftermath_bench.integrations.forgejo_promotion_baselines import (
    FORGEJO_PROMOTION_BASELINES,
    run_fixed_forgejo_promotion_baseline,
)
from aftermath_bench.integrations.forgejo_promotion_evaluator import (
    promotion_components,
)


class ForgejoPromotionAgentTest(unittest.TestCase):
    def test_comment_body_is_diagnostic_not_a_hidden_hard_constraint(self) -> None:
        checks = {
            "production_deployed": True,
            "two_matching_ready_replicas": True,
            "attestation_exactly_once": True,
            "target_release_published_once": True,
            "rollout_issue_closed": True,
            "native_actions_artifact_present": True,
            "signed_bundle_registered_once": True,
            "prior_release_preserved": True,
            "approval_record_preserved": True,
            "unrelated_issue_preserved": True,
            "protected_environment_preserved": True,
            "single_successful_promotion_owner": True,
            "verification_comment_exactly_once": False,
        }
        self.assertTrue(all(promotion_components(checks).values()))

    @staticmethod
    def _environment_with_runs(runs):
        forgejo = Mock()
        forgejo.list_action_runs.return_value = runs
        return ForgejoPromotionEnvironment(
            forgejo=forgejo,
            deployment=Mock(),
            stack=Mock(),
            instance=SimpleNamespace(owner="aftermath", repository="service"),
            prefix={},
            variant="hidden-label-must-not-decide-gold",
        )

    def test_public_surface_has_cross_system_reads_without_repair_tool(self) -> None:
        names = set(ForgejoPromotionEnvironment.TOOL_NAMES)
        self.assertTrue(
            {
                "list_action_runs",
                "list_action_run_artifacts",
                "get_deployment_state",
                "get_external_attestation",
                "dispatch_workflow",
                "get_action_artifact_manifest",
            }.issubset(names)
        )
        self.assertFalse(any(name.startswith("repair_") for name in names))

    def test_artifact_manifest_exposes_file_hashes_not_an_answer_label(self) -> None:
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("binary.tar.gz", b"approved bytes")
        forgejo = Mock()
        forgejo.list_action_run_artifacts.return_value = [
            {"id": 9, "name": "approved-6.2.0"}
        ]
        forgejo.download_action_artifact.return_value = archive.getvalue()
        manifest = inspect_action_artifact(
            forgejo,
            owner="aftermath",
            repository="service",
            run_id=7,
            artifact_id=9,
        )
        self.assertEqual(manifest["artifact_name"], "approved-6.2.0")
        self.assertEqual(manifest["files"][0]["name"], "binary.tar.gz")
        self.assertEqual(len(manifest["files"][0]["sha256"]), 64)

    def test_waiting_for_a_run_is_classified_as_state_advancing(self) -> None:
        self.assertIn(
            "wait_for_action_run", ForgejoPromotionEnvironment.MUTATION_TOOLS
        )

    def test_expected_owner_count_is_derived_from_boundary_state(self) -> None:
        self.assertEqual(self._environment_with_runs([]).expected_action_run_count, 1)
        self.assertEqual(
            self._environment_with_runs([{"id": 7, "status": "waiting"}])
            .expected_action_run_count,
            1,
        )
        self.assertEqual(
            self._environment_with_runs([{"id": 7, "status": "failure"}])
            .expected_action_run_count,
            2,
        )
        self.assertEqual(
            self._environment_with_runs([{"id": 7, "status": "success"}])
            .expected_action_run_count,
            1,
        )

    def test_fixed_baselines_are_state_insensitive_and_distinct(self) -> None:
        traces = {}
        for baseline in FORGEJO_PROMOTION_BASELINES:
            environment = Mock()
            environment.instance = SimpleNamespace(
                workflow_path=".forgejo/workflows/promote.yml",
                version="6.2.0",
                artifact_digest="sha256:approved",
                attestation_key="attestation:key",
                release_tag="v6.2.0",
            )
            environment.prefix = {"rollout_issue_index": 2}

            def invoke(tool: str, **arguments):
                if tool == "list_action_runs":
                    return {"ok": True, "result": [{"id": 7}]}
                if tool == "dispatch_workflow":
                    return {"ok": True, "result": {"id": 8}}
                return {"ok": True, "result": {}}

            environment.invoke.side_effect = invoke
            traces[baseline] = run_fixed_forgejo_promotion_baseline(
                baseline, environment=environment
            )

        self.assertEqual(traces["no_op"], ())
        self.assertNotEqual(
            traces["resume_after_bundle"], traces["resume_after_deployment"]
        )
        self.assertTrue(
            any(
                event["tool"] == "start_action_runner"
                for event in traces["start_runner_then_finalize"]
            )
        )


if __name__ == "__main__":
    unittest.main()
