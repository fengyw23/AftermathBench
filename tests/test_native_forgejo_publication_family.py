from __future__ import annotations

import unittest

from aftermath_bench.native_forgejo_publication_family import (
    FORGEJO_PUBLICATION_FAMILY,
    FORGEJO_PUBLICATION_TOOL_DEFINITIONS,
    forgejo_publication_initial_message,
)
from aftermath_bench.native_model_runner import NATIVE_FAMILY_REGISTRY
from aftermath_bench.native_scenario import load_native_scenario
from aftermath_bench.schema import repository_root


class NativeForgejoPublicationFamilyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "forgejo-release-publication-dev-002"
            / "scenario.json"
        )
        self.prefix = {
            "owner": "aftermath",
            "repository": "artifact-publication",
            "base_branch": "release/2026.08",
            "pull_request_index": 2,
            "linked_issue_index": 1,
            "milestone_id": 1,
            "release_tag": "v2026.08.0",
            "protected_pull_request_index": 3,
            "protected_issue_index": 4,
            "protected_release_tag": "v2026.07.3",
            "coordinator_hook_id": 7,
            "provenance_hook_id": 8,
            "trace": [],
        }

    def test_family_is_manifest_routable(self) -> None:
        self.assertIs(
            NATIVE_FAMILY_REGISTRY.get(
                "forgejo-release-package-publication"
            ),
            FORGEJO_PUBLICATION_FAMILY,
        )

    def test_tools_are_closed_and_not_answer_style(self) -> None:
        for tool in FORGEJO_PUBLICATION_TOOL_DEFINITIONS:
            self.assertFalse(tool.input_schema["additionalProperties"])
            self.assertNotIn("repair", tool.name)
            self.assertNotIn("recommend", tool.name)

    def test_ordinary_prompt_hides_variant_and_scope(self) -> None:
        failure = {
            "variant": (
                "release_committed_coordinator_accepted_provenance_missing"
            ),
            "visible_failure": {"ok": False, "error": "connection lost"},
        }
        message = forgejo_publication_initial_message(
            scenario=self.scenario,
            prefix=self.prefix,
            failure_report=failure,
        )
        self.assertNotIn(failure["variant"], message)
        self.assertNotIn("replay only", message.lower())
        self.assertIn("connection lost", message)


if __name__ == "__main__":
    unittest.main()
