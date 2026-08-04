from __future__ import annotations

import unittest
from types import SimpleNamespace

from aftermath_bench.integrations.forgejo_reconciliation_baselines import (
    FORGEJO_RECONCILIATION_BASELINES,
    run_fixed_forgejo_reconciliation_baseline,
)


class FakeEnvironment:
    def __init__(self) -> None:
        self.instance = SimpleNamespace(
            workflow_path=".forgejo/workflows/promote.yml",
            repository="service",
            version="1.2.3",
            release_tag="v1.2.3",
            artifact_digest="sha256:approved",
            attestation_key="attestation:key",
        )
        self.prefix = {
            "rollout_issue_index": 7,
            "repository_head": "native-head",
        }
        self.calls: list[tuple[str, dict]] = []
        self.dispatched = False

    def invoke(self, tool: str, **arguments):
        self.calls.append((tool, arguments))
        if tool == "list_action_runs":
            return {
                "ok": True,
                "result": ([{"id": 9, "status": "failure"}] if self.dispatched else []),
            }
        if tool == "dispatch_workflow":
            self.dispatched = True
        return {"ok": True, "result": {}}


class ForgejoReconciliationBaselinesTest(unittest.TestCase):
    def test_each_baseline_name_is_executable(self) -> None:
        for name in FORGEJO_RECONCILIATION_BASELINES:
            with self.subTest(name=name):
                environment = FakeEnvironment()
                trace = run_fixed_forgejo_reconciliation_baseline(
                    name, environment=environment
                )
                self.assertIsInstance(trace, tuple)

    def test_targeted_policies_use_distinct_native_resume_inputs(self) -> None:
        expected = {
            "repair_actions_only": ("start", "artifact"),
            "repair_registry_only": ("after_artifact", "bundle"),
            "repair_production_only": ("after_bundle", "deployment"),
            "repair_attestation_only": ("after_deployment", "none"),
        }
        for name, pair in expected.items():
            with self.subTest(name=name):
                environment = FakeEnvironment()
                run_fixed_forgejo_reconciliation_baseline(
                    name, environment=environment
                )
                dispatch = next(
                    arguments
                    for tool, arguments in environment.calls
                    if tool == "dispatch_workflow"
                )
                self.assertEqual(
                    (
                        dispatch["inputs"]["resume_stage"],
                        dispatch["inputs"]["stop_after"],
                    ),
                    pair,
                )
                self.assertEqual(
                    dispatch["inputs"]["source_commit"], "native-head"
                )

    def test_metadata_policy_binds_digest_and_attestation(self) -> None:
        environment = FakeEnvironment()
        run_fixed_forgejo_reconciliation_baseline(
            "repair_metadata_only", environment=environment
        )
        release = next(
            arguments
            for tool, arguments in environment.calls
            if tool == "create_release"
        )
        self.assertIn(environment.instance.artifact_digest, release["body"])
        self.assertIn(environment.instance.attestation_key, release["body"])


if __name__ == "__main__":
    unittest.main()
