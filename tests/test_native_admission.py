import hashlib
import unittest

from aftermath_bench.native_admission import (
    _constraint_prompt_admission,
    _reference_evidence_groups,
    validate_native_scenario,
)
from aftermath_bench.native_scenario import (
    load_native_scenario,
    native_scenario_paths,
)


class NativeAdmissionTest(unittest.TestCase):
    def _constraint_audit(self) -> dict:
        texts = {
            "user_instruction": "Restore consistent service without repeating effects.",
            "system_prompt": "Inspect authoritative state before writes.",
            "change_authorization": "The current change window is closed.",
            "schema_policy": "Committed schema epochs cannot move backward.",
            "event_contract": "External effects use idempotency keys.",
            "tool_descriptions": "Read and mutate ordinary native objects.",
        }
        surfaces = [
            {
                "id": key,
                "text": text,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            for key, text in texts.items()
        ]
        variants = ("a", "b", "c", "d")
        return {
            "visible_surfaces": surfaces,
            "required_surface_ids": list(texts),
            "forbidden_direction_labels": [
                "rollback_to_stable",
                "compensate_external_effect",
                "forward_complete",
                "repair_downstream_only",
            ],
            "constraint_evidence_groups": [
                {"id": "authorization", "surface_ids": ["change_authorization"]},
                {"id": "schema", "surface_ids": ["schema_policy"]},
                {"id": "external", "surface_ids": ["event_contract"]},
                {"id": "serving", "surface_ids": ["tool_descriptions"]},
            ],
            "constraints": [
                {
                    "id": "closed_window",
                    "surface_ids": ["change_authorization"],
                },
                {
                    "id": "schema_monotonicity",
                    "surface_ids": ["schema_policy"],
                },
                {
                    "id": "external_exactly_once",
                    "surface_ids": ["event_contract"],
                },
            ],
            "variant_derivations": [
                {
                    "variant": variant,
                    "evidence_groups": ["authorization", "schema", "external"],
                    "constraint_ids": ["closed_window", "schema_monotonicity"],
                    "decisive_surface_ids": [
                        "change_authorization",
                        "schema_policy",
                        "event_contract",
                    ],
                }
                for variant in variants
            ],
            "counterfactual_pairs": [
                {
                    "left": "a",
                    "right": "b",
                    "changed_fact_count": 1,
                    "direction_flipped": True,
                },
                {
                    "left": "c",
                    "right": "d",
                    "changed_fact_count": 1,
                    "direction_flipped": True,
                },
            ],
        }

    def test_constraint_prompt_profile_accepts_composed_visible_evidence(self) -> None:
        checks, observed = _constraint_prompt_admission(
            self._constraint_audit(),
            minimum_counterfactual_flips=2,
            expected_variants={"a", "b", "c", "d"},
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(observed["ordinary_direction_label_leak_count"], 0)
        self.assertEqual(observed["minimum_derivation_evidence_groups"], 3)

    def test_constraint_prompt_profile_rejects_direction_label_leakage(self) -> None:
        audit = self._constraint_audit()
        audit["visible_surfaces"][2]["text"] += " rollback-to-stable"
        audit["visible_surfaces"][2]["sha256"] = hashlib.sha256(
            audit["visible_surfaces"][2]["text"].encode("utf-8")
        ).hexdigest()
        checks, observed = _constraint_prompt_admission(
            audit,
            minimum_counterfactual_flips=2,
            expected_variants={"a", "b", "c", "d"},
        )
        self.assertFalse(checks["ordinary_direction_labels_not_leaked"])
        self.assertEqual(observed["ordinary_direction_label_leak_count"], 1)

    def test_constraint_prompt_profile_rejects_single_surface_derivation(self) -> None:
        audit = self._constraint_audit()
        audit["variant_derivations"][0]["decisive_surface_ids"] = [
            "change_authorization"
        ]
        checks, _ = _constraint_prompt_admission(
            audit,
            minimum_counterfactual_flips=2,
            expected_variants={"a", "b", "c", "d"},
        )
        self.assertFalse(checks["no_single_visible_surface_is_decisive"])

    def test_domain_specific_evidence_groups_are_tool_driven(self) -> None:
        graph = {
            "evidence_tool_groups": [
                {"id": "objects", "tools": ["get_object", "list_objects"]},
                {"id": "events", "tools": ["list_events"]},
                {"id": "logs", "tools": ["get_job_logs"]},
                {
                    "id": "external",
                    "tools": ["list_external_deliveries"],
                },
            ]
        }
        groups = _reference_evidence_groups(
            {
                "list_objects",
                "list_events",
                "get_job_logs",
                "list_external_deliveries",
            },
            graph,
        )
        self.assertTrue(all(groups.values()))

    def test_directional_profile_cannot_be_faked_by_tool_signatures(self) -> None:
        reports = [
            {
                "mutation_tools": ["patch_object"] * count,
                "semantic_recovery_direction": "forward_complete",
            }
            for count in (1, 2, 3, 4)
        ]
        directions = {report["semantic_recovery_direction"] for report in reports}
        signatures = {tuple(report["mutation_tools"]) for report in reports}
        self.assertEqual(len(signatures), 4)
        self.assertEqual(len(directions), 1)

    def test_argument_scoped_query_groups_require_distinct_native_reads(self) -> None:
        graph = {
            "evidence_tool_groups": [
                {
                    "id": "catalog",
                    "calls": [
                        {
                            "tool": "get_object",
                            "arguments": {"name": "database-catalog"},
                        }
                    ],
                },
                {
                    "id": "routing",
                    "calls": [
                        {
                            "tool": "list_objects",
                            "arguments": {"resource": "services"},
                        }
                    ],
                },
            ]
        }
        groups = _reference_evidence_groups(
            {
                "query_tools": ["get_object"],
                "query_events": [
                    {
                        "tool": "get_object",
                        "arguments": {"name": "database-catalog"},
                    }
                ],
            },
            graph,
        )
        self.assertTrue(groups["catalog"])
        self.assertFalse(groups["routing"])

    def test_payment_pilot_is_truthfully_classified_easy(self) -> None:
        path = next(
            path
            for path in native_scenario_paths()
            if path.parent.name == "erpnext-procurement-payment-001"
        )
        report = validate_native_scenario(load_native_scenario(path))
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.requested_tier, "easy")
        self.assertEqual(report.admitted_tier, "easy")
        self.assertFalse(report.checks["minimum_mutations>=4"])
        self.assertFalse(report.checks["no_single_query_is_decisive"])
        self.assertFalse(report.checks["heuristic_pass_rate<0.5"])

    def test_kubernetes_partial_downstream_replay_is_hard_admitted(self) -> None:
        path = next(
            path
            for path in native_scenario_paths()
            if path.parent.name == "k8s-settlement-orchestrated-dev-002"
        )
        report = validate_native_scenario(load_native_scenario(path))
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.admitted_tier, "hard")
        self.assertEqual(report.observed["relevant_entity_count"], 23)
        self.assertEqual(report.observed["replayed_relation_count"], 23)
        self.assertEqual(report.observed["maximum_heuristic_pass_rate"], 0.25)


if __name__ == "__main__":
    unittest.main()
