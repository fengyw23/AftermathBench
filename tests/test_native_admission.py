import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.native_admission import (
    _adaptive_query_depth,
    _constraint_prompt_admission,
    _projection_witness_admission,
    _recovery_divergence,
    _reference_evidence_groups,
    native_admission_report_payload,
    validate_native_scenario,
)
from aftermath_bench.native_scenario import (
    load_native_scenario,
    native_scenario_paths,
)
from aftermath_bench.schema import repository_root
from scripts.refresh_native_admission_report import (
    refresh_native_admission_report,
)


class NativeAdmissionTest(unittest.TestCase):
    def test_adaptive_query_depth_requires_result_derived_arguments(self) -> None:
        report = {
            "query_events": [
                {
                    "tool": "list_runs",
                    "arguments": {},
                    "result": [{"id": 73, "status": "waiting"}],
                },
                {
                    "tool": "get_run",
                    "arguments": {"run_id": 73},
                    "result": {"id": 73, "job_id": 811, "status": "waiting"},
                },
                {
                    "tool": "get_job",
                    "arguments": {"job_id": 811},
                    "result": {"id": 811, "status": "queued"},
                },
                {
                    "tool": "get_job",
                    "arguments": {"job_id": 811},
                    "result": {"id": 811, "status": "success"},
                },
            ]
        }
        self.assertEqual(_adaptive_query_depth(report), 3)

    def test_repeated_polling_does_not_inflate_adaptive_depth(self) -> None:
        report = {
            "query_events": [
                {
                    "tool": "list_runs",
                    "arguments": {},
                    "result": [{"id": 73}],
                },
                *[
                    {
                        "tool": "get_run",
                        "arguments": {"run_id": 73},
                        "result": {"id": 73, "status": status},
                    }
                    for status in ("queued", "running", "success")
                ],
            ]
        }
        self.assertEqual(_adaptive_query_depth(report), 2)

    def test_json_document_content_can_drive_followup_reads(self) -> None:
        report = {
            "query_events": [
                {
                    "tool": "get_manifest",
                    "arguments": {"path": "release/manifest.json"},
                    "result": {
                        "content": '{"assets":[{"source_path":"dist/app.sig"}]}'
                    },
                },
                {
                    "tool": "get_file",
                    "arguments": {"path": "dist/app.sig"},
                    "result": {"sha256": "abcdef1234567890"},
                },
            ]
        }
        self.assertEqual(_adaptive_query_depth(report), 2)

    def test_recovery_divergence_separates_branch_work_from_common_tail(self) -> None:
        reports = [
            {
                "mutation_events": [
                    {"tool": "repair", "arguments": {"part": "a"}},
                    {"tool": "verify", "arguments": {"part": "a"}},
                    {"tool": "close", "arguments": {}},
                ]
            },
            {
                "mutation_events": [
                    {"tool": "repair", "arguments": {"part": "b"}},
                    {"tool": "verify", "arguments": {"part": "b"}},
                    {"tool": "close", "arguments": {}},
                ]
            },
        ]
        common_tail, branch_mutations, pairwise_distance = _recovery_divergence(reports)
        self.assertEqual(common_tail, 1)
        self.assertEqual(branch_mutations, 2)
        self.assertEqual(pairwise_distance, 2)

    def test_easy_parallel_read_pattern_fails_adaptive_recovery_profile(self) -> None:
        source = (
            repository_root()
            / "data"
            / "scenarios"
            / "forgejo-migration-deployment-public-dev-001"
        )
        with tempfile.TemporaryDirectory() as directory:
            scenario_root = Path(directory) / source.name
            shutil.copytree(source, scenario_root)
            scenario_path = scenario_root / "scenario.json"
            payload = json.loads(scenario_path.read_text(encoding="utf-8"))
            payload["admission_profile"] = {
                "adaptive_recovery": {
                    "minimum_adaptive_query_depth": 2,
                    "minimum_variant_specific_mutations": 2,
                    "minimum_pairwise_mutation_distance": 2,
                }
            }
            scenario_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            report = validate_native_scenario(load_native_scenario(scenario_path))

            self.assertFalse(report.passed)
            self.assertFalse(
                report.checks["reference_queries_include_replayed_results"]
            )
            self.assertFalse(report.checks["adaptive_query_depth_meets_profile"])
            self.assertFalse(report.checks["variant_specific_mutations_meet_profile"])
            self.assertFalse(report.checks["pairwise_mutation_distance_meets_profile"])
            self.assertEqual(report.observed["minimum_adaptive_query_depth"], 0)
            self.assertEqual(report.observed["minimum_variant_specific_mutations"], 0)
            self.assertEqual(report.observed["minimum_pairwise_mutation_distance"], 0)

    def test_scope_decision_profile_rejects_single_query_solver(self) -> None:
        source = (
            repository_root()
            / "data"
            / "scenarios"
            / "forgejo-package-provenance-nonmonotonic-dev-001"
        )
        with tempfile.TemporaryDirectory() as directory:
            scenario_root = Path(directory) / source.name
            shutil.copytree(source, scenario_root)
            scenario_path = scenario_root / "scenario.json"
            payload = json.loads(scenario_path.read_text(encoding="utf-8"))
            payload["admission_profile"]["scope_decision"] = {
                "minimum_adaptive_worst_case_depth": 2,
                "minimum_static_certificate_size": 2,
            }
            payload["admission_artifacts"]["scope_decision_matrix"] = (
                "artifacts/scope-decision-matrix.json"
            )
            scenario_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            rows = [
                {
                    "variant": variant,
                    "recovery_signature": f"scope-{index}",
                    "observations": {
                        "package_inventory": f"state-{index}",
                        "constant_policy": "same",
                    },
                }
                for index, variant in enumerate(payload["matched_variants"])
            ]
            matrix_path = scenario_root / "artifacts" / "scope-decision-matrix.json"
            matrix_path.write_text(
                json.dumps(
                    {
                        "scenario_id": payload["scenario_id"],
                        "rows": rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = validate_native_scenario(load_native_scenario(scenario_path))

            self.assertFalse(report.passed)
            self.assertTrue(report.checks["scope_decision_matrix_valid"])
            self.assertFalse(
                report.checks["scope_decision_static_certificate_meets_profile"]
            )
            self.assertFalse(
                report.checks["scope_decision_adaptive_depth_meets_profile"]
            )
            self.assertFalse(
                report.checks["scope_decision_has_no_single_surface_solver"]
            )
            self.assertEqual(
                report.observed["scope_decision_optimal_adaptive_depth"], 1
            )

    def test_obligation_profile_rejects_unbound_action_probe(self) -> None:
        source = (
            repository_root()
            / "data"
            / "scenarios"
            / "forgejo-package-provenance-nonmonotonic-dev-001"
        )
        with tempfile.TemporaryDirectory() as directory:
            scenario_root = Path(directory) / source.name
            shutil.copytree(source, scenario_root)
            scenario_path = scenario_root / "scenario.json"
            payload = json.loads(scenario_path.read_text(encoding="utf-8"))
            payload["admission_profile"]["obligation_interaction"] = {
                "minimum_obligation_count": 2,
                "minimum_protected_obligation_count": 1,
                "minimum_gold_scope_count": 2,
                "minimum_cross_obligation_witnesses": 0,
                "minimum_repair_preservation_conflict_witnesses": 0,
                "minimum_variants_with_conflict": 0,
            }
            payload["admission_artifacts"]["obligation_interactions"] = (
                "artifacts/obligation-interactions.json"
            )
            scenario_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            rows = []
            for index, variant in enumerate(payload["matched_variants"]):
                action = "keep" if index % 2 == 0 else "rebuild"
                rows.append(
                    {
                        "variant": variant,
                        "boundary_evaluation": {
                            "failed_goal": False,
                            "protected_release": True,
                        },
                        "gold_action_ids": [action],
                        "probes": [
                            {
                                "action_id": action,
                                "tool_events": [
                                    {"tool": "repair", "arguments": {"mode": action}}
                                ],
                                "result_state_sha256": "not-a-native-hash",
                                "result_evaluation": {
                                    "failed_goal": True,
                                    "protected_release": True,
                                },
                            }
                        ],
                    }
                )
            artifact_path = (
                scenario_root / "artifacts" / "obligation-interactions.json"
            )
            artifact_path.write_text(
                json.dumps(
                    {
                        "scenario_id": payload["scenario_id"],
                        "obligations": [
                            {"id": "failed_goal", "protected": False},
                            {"id": "protected_release", "protected": True},
                        ],
                        "actions": [{"id": "keep"}, {"id": "rebuild"}],
                        "rows": rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            report = validate_native_scenario(load_native_scenario(scenario_path))

            self.assertFalse(report.passed)
            self.assertTrue(report.checks["obligation_interaction_artifact_valid"])
            self.assertFalse(
                report.checks["obligation_interaction_probes_replay_bound"]
            )
            self.assertIn("obligation_interactions", report.artifact_sha256)

    def test_derived_admission_report_is_not_a_recursive_input(self) -> None:
        source = (
            repository_root()
            / "data"
            / "scenarios"
            / "forgejo-release-publication-dev-002"
        )
        with tempfile.TemporaryDirectory() as directory:
            scenario_root = Path(directory) / source.name
            shutil.copytree(source, scenario_root)
            (scenario_root / "artifacts" / "admission.json").unlink()

            report = validate_native_scenario(
                load_native_scenario(scenario_root / "scenario.json")
            )

            self.assertTrue(report.passed, report.failures)
            self.assertNotIn("admission", report.artifact_sha256)
            self.assertTrue(report.checks["artifact_scenario_ids_match"])
            persisted = refresh_native_admission_report(scenario_root / "scenario.json")
            self.assertEqual(
                persisted,
                native_admission_report_payload(report),
            )
            replayed = validate_native_scenario(
                load_native_scenario(scenario_root / "scenario.json")
            )
            self.assertEqual(replayed, report)

    def test_projection_profile_requires_valid_witness_for_every_group(self) -> None:
        report = {
            "variant_ids": ["a", "b", "c"],
            "evidence_group_count": 2,
            "all_declared_groups_have_witnesses": True,
            "witnesses": {
                "commit": {
                    "left_variant": "a",
                    "right_variant": "b",
                    "left_scope": "keep",
                    "right_scope": "discard",
                    "removed_fact_keys": ["committed"],
                },
                "publication": {
                    "left_variant": "b",
                    "right_variant": "c",
                    "left_scope": "discard",
                    "right_scope": "publish",
                    "removed_fact_keys": ["published"],
                },
            },
        }
        checks, observed = _projection_witness_admission(
            report,
            expected_variants={"a", "b", "c"},
            minimum_witnesses=2,
        )
        self.assertTrue(all(checks.values()), checks)
        self.assertEqual(observed["valid_projection_witness_count"], 2)

    def test_projection_profile_rejects_redundant_declared_group(self) -> None:
        report = {
            "variant_ids": ["a", "b"],
            "evidence_group_count": 2,
            "all_declared_groups_have_witnesses": False,
            "witnesses": {
                "commit": {
                    "left_variant": "a",
                    "right_variant": "b",
                    "left_scope": "keep",
                    "right_scope": "discard",
                    "removed_fact_keys": ["committed"],
                },
                "region": None,
            },
        }
        checks, _ = _projection_witness_admission(
            report,
            expected_variants={"a", "b"},
            minimum_witnesses=2,
        )
        self.assertFalse(checks["projection_witnesses_meet_profile"])
        self.assertFalse(checks["every_declared_evidence_group_has_projection_witness"])

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

    def test_partial_return_pilot_is_truthfully_classified_easy(self) -> None:
        path = next(
            path
            for path in native_scenario_paths()
            if path.parent.name == "erpnext-partial-return-dev-001"
        )
        report = validate_native_scenario(load_native_scenario(path))
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.requested_tier, "easy")
        self.assertEqual(report.admitted_tier, "easy")
        self.assertFalse(report.checks["relevant_entities>=20"])
        self.assertFalse(report.checks["minimum_mutations>=4"])
        self.assertFalse(report.checks["action_branches>=3"])

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
