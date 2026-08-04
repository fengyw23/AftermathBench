from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace

from aftermath_bench.integrations.forgejo_reconciliation_recovery import (
    evaluate_reconciliation_terminal,
    project_reconciliation_obligations,
)


class ForgejoReconciliationRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.instance = SimpleNamespace(
            version="6.2.0",
            approved_commit="approved",
            artifact_digest="sha256:approved",
            attestation_key="transparency:service:v6.2.0",
            production_environment="production",
            protected_environment="canary",
            release_tag="v6.2.0",
            protected_release_tag="v6.1.4",
        )
        protected_deployment = {
            "environment": "canary",
            "desired_version": "next",
            "artifact_digest": "sha256:canary",
            "status": "deployed",
        }
        protected_replicas = [
            {
                "environment": "canary",
                "replica": name,
                "version": "next",
                "artifact_digest": "sha256:canary",
                "status": "ready",
            }
            for name in ("a", "b")
        ]
        self.prefix = {
            "rollout_issue_index": 2,
            "protected_state": {
                "deployments": [protected_deployment],
                "replicas": protected_replicas,
            },
        }
        self.state = {
            "runs": [{"id": 1}],
            "action_artifacts": [
                {"name": "approved-6.2.0", "expired": False}
            ],
            "approval_source_manifest": {
                "binary.tar.gz": {"size": 1, "sha256": "binary"}
            },
            "action_artifact_manifests": [
                {
                    "files": [
                        {"name": "binary.tar.gz", "size": 1, "sha256": "binary"}
                    ]
                }
            ],
            "deployment_state": {
                "artifacts": [
                    {
                        "version": "6.2.0",
                        "digest": "sha256:approved",
                        "source_commit": "approved",
                        "attempt_count": 1,
                    }
                ],
                "deployments": [
                    protected_deployment,
                    {
                        "environment": "production",
                        "desired_version": "6.2.0",
                        "artifact_digest": "sha256:approved",
                        "status": "deployed",
                    },
                ],
                "replicas": [
                    *protected_replicas,
                    *[
                        {
                            "environment": "production",
                            "replica": name,
                            "version": "6.2.0",
                            "artifact_digest": "sha256:approved",
                            "status": "ready",
                        }
                        for name in ("a", "b")
                    ],
                ],
            },
            "external_attestation": {
                "attempt_count": 1,
                "payload": {"artifact_digest": "sha256:approved"},
            },
            "releases": [
                {"tag_name": "v6.1.4"},
                {
                    "tag_name": "v6.2.0",
                    "body": (
                        "Approved sha256:approved and "
                        "transparency:service:v6.2.0 are live."
                    ),
                    "draft": False,
                },
            ],
            "issues": [{"number": 2, "state": "closed"}],
            "comments": [],
        }

    def test_all_valid_state_passes(self) -> None:
        result = evaluate_reconciliation_terminal(
            self.state, instance=self.instance, prefix=self.prefix
        )
        self.assertTrue(result["passed"])

    def test_each_single_gap_changes_only_its_obligation(self) -> None:
        mutations = {
            "actions_bundle_matches_approval": lambda state: state[
                "action_artifact_manifests"
            ].clear(),
            "artifact_registry_matches_bundle": lambda state: state[
                "deployment_state"
            ]["artifacts"].clear(),
            "production_matches_registry": lambda state: state["deployment_state"][
                "replicas"
            ].__setitem__(
                slice(None),
                [
                    row
                    for row in state["deployment_state"]["replicas"]
                    if row["environment"] != "production"
                ],
            ),
            "attestation_matches_production": lambda state: state.__setitem__(
                "external_attestation", None
            ),
            "release_metadata_matches_all_effects": lambda state: state["releases"].pop(),
        }
        for expected, mutate in mutations.items():
            with self.subTest(expected=expected):
                state = copy.deepcopy(self.state)
                mutate(state)
                projection = project_reconciliation_obligations(
                    state, instance=self.instance, prefix=self.prefix
                )
                self.assertEqual(
                    [name for name, valid in projection.items() if not valid],
                    [expected],
                )

    def test_release_metadata_is_semantic_not_presence_only(self) -> None:
        for body in (
            "release complete",
            "sha256:approved deployed",
            "transparency:service:v6.2.0 accepted",
        ):
            with self.subTest(body=body):
                state = copy.deepcopy(self.state)
                state["releases"][1]["body"] = body
                projection = project_reconciliation_obligations(
                    state, instance=self.instance, prefix=self.prefix
                )
                self.assertFalse(
                    projection["release_metadata_matches_all_effects"]
                )

        state = copy.deepcopy(self.state)
        state["releases"][1]["body"] = (
            "transparency:service:v6.2.0 accepted; production is "
            "sha256:approved."
        )
        projection = project_reconciliation_obligations(
            state, instance=self.instance, prefix=self.prefix
        )
        self.assertTrue(projection["release_metadata_matches_all_effects"])


if __name__ == "__main__":
    unittest.main()
