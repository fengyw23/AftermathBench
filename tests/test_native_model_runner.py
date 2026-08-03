import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from aftermath_bench.hidden_test_eligibility import (
    begin_hidden_test_evaluation,
)
from aftermath_bench.native_freeze import append_usage_event, file_sha256
from aftermath_bench.native_model_runner import (
    NATIVE_FAMILY_REGISTRY,
    NATIVE_RETURN_TOOL_DEFINITIONS,
    _diagnose,
    _pre_model_boundary_matches_lock,
    native_initial_message,
    run_live_native_agent,
    run_native_family_agent,
)
from aftermath_bench.native_scenario import NativeScenario, load_native_scenario
from aftermath_bench.schema import repository_root


class NativeModelRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = load_native_scenario(
            repository_root()
            / "data"
            / "scenarios"
            / "erpnext-partial-return-dev-001"
            / "scenario.json"
        )

    def test_input_never_reveals_hidden_variant(self) -> None:
        prefix = {
            "company": "Aftermath Laboratories LLC",
            "supplier": "Northwind Scientific",
            "purchase_return": "PR-RET-1",
            "trace": [{"kind": "write", "tool": "create return"}],
        }
        message = native_initial_message(
            scenario=self.scenario,
            prefix=prefix,
            failure_report={
                "visible_failure": {
                    "ok": False,
                    "error": "connection_lost_before_confirmation",
                }
            },
        )
        self.assertIn("PR-RET-1", message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)

    def test_pre_model_lock_accepts_only_trusted_semantic_equivalence(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            locked_path = root / "data" / "formal" / "boundary.json"
            live_path = root / "data" / "generated" / "boundary.json"
            locked_path.parent.mkdir(parents=True)
            live_path.parent.mkdir(parents=True)
            locked_path.write_text('{"state":"locked"}\n', encoding="utf-8")
            live_path.write_text('{"state":"live"}\n', encoding="utf-8")
            locked_hash = hashlib.sha256(locked_path.read_bytes()).hexdigest()
            live_hash = hashlib.sha256(live_path.read_bytes()).hexdigest()

            with patch(
                "aftermath_bench.native_model_runner."
                "native_boundaries_equivalent",
                return_value=True,
            ) as equivalent:
                self.assertTrue(
                    _pre_model_boundary_matches_lock(
                        root=root,
                        family_id="erpnext-manufacturing-rework",
                        locked_boundary_sha256=locked_hash,
                        locked_boundary_path="data/formal/boundary.json",
                        evidence_path=live_path,
                        evidence_sha256=live_hash,
                    )
                )
            equivalent.assert_called_once_with(
                "erpnext-manufacturing-rework",
                {"state": "locked"},
                {"state": "live"},
            )
            self.assertFalse(
                _pre_model_boundary_matches_lock(
                    root=root,
                    family_id="unregistered-family",
                    locked_boundary_sha256=locked_hash,
                    locked_boundary_path=None,
                    evidence_path=live_path,
                    evidence_sha256=live_hash,
                )
            )

    def test_tools_are_generic_and_schemas_are_closed(self) -> None:
        names = {tool.name for tool in NATIVE_RETURN_TOOL_DEFINITIONS}
        self.assertIn("get_document", names)
        self.assertIn("list_related_documents", names)
        self.assertIn("submit_document", names)
        self.assertNotIn("repair_purchase_return", names)
        self.assertNotIn("get_recommended_action", names)
        list_documents = next(
            tool
            for tool in NATIVE_RETURN_TOOL_DEFINITIONS
            if tool.name == "list_documents"
        )
        self.assertIn(
            "Webhook",
            list_documents.input_schema["properties"]["doctype"]["enum"],
        )
        for tool in NATIVE_RETURN_TOOL_DEFINITIONS:
            self.assertFalse(tool.input_schema["additionalProperties"])
            self.assertNotIn("hidden", json.dumps(tool.input_schema).lower())

    def test_native_family_is_selected_from_registry(self) -> None:
        family = NATIVE_FAMILY_REGISTRY.get(self.scenario.raw["family"])
        self.assertEqual(family.domain, "erpnext")
        self.assertEqual(
            family.tool_definitions,
            NATIVE_RETURN_TOOL_DEFINITIONS,
        )
        with self.assertRaisesRegex(ValueError, "unsupported native family"):
            NATIVE_FAMILY_REGISTRY.get("nonexistent-family")

    @staticmethod
    def _stub_family_and_environment():
        evaluation = SimpleNamespace(
            passed=True,
            components={},
            checks={},
            diagnostics={},
            failures=[],
        )
        family = SimpleNamespace(
            system_prompt="Use tools for at most {max_turns} turns.",
            tool_definitions=(),
            family_id="test-family",
            domain="test",
            build_initial_message=lambda **_: "Recover the task.",
            evaluate=lambda *_: evaluation,
            diagnose=lambda **_: {},
        )
        environment = SimpleNamespace(
            snapshot=dict,
            event_log=list,
        )
        return family, environment

    @staticmethod
    def _stub_client():
        calls = []

        def complete(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                text="done",
                tool_calls=(),
                usage={},
                stop_reason="stop",
                raw_response={},
            )

        return (
            SimpleNamespace(
                provider="openai-compatible",
                model="test-model",
                complete=complete,
            ),
            calls,
        )

    def test_direct_hidden_family_run_fails_before_provider_access(self) -> None:
        client, calls = self._stub_client()
        scenario = NativeScenario(
            path=Path("hidden-scenario.json"),
            raw={
                "scenario_id": "hidden-001",
                "benchmark_split": "hidden_test",
                "matched_variants": [{"id": "state-1"}],
            },
        )
        with self.assertRaisesRegex(
            RuntimeError,
            "runner-managed evaluation lock",
        ):
            run_native_family_agent(
                client,
                family=SimpleNamespace(),
                scenario=scenario,
                environment=SimpleNamespace(),
                prefix={},
                failure_report={},
            )
        self.assertEqual(calls, [])

    def test_development_family_run_needs_no_hidden_lock(self) -> None:
        client, calls = self._stub_client()
        family, environment = self._stub_family_and_environment()
        scenario = NativeScenario(
            path=Path("development-scenario.json"),
            raw={
                "scenario_id": "development-001",
                "benchmark_split": "development",
                "matched_variants": [{"id": "state-1"}],
            },
        )
        report = run_native_family_agent(
            client,
            family=family,
            scenario=scenario,
            environment=environment,
            prefix={},
            failure_report={
                "variant": "state-1",
                "visible_failure": {"error": "connection lost"},
            },
            max_turns=1,
        )
        self.assertEqual(len(calls), 1)
        self.assertTrue(report["evaluation"]["passed"])

    def test_family_run_accepts_latest_attempt_boundary_layout(self) -> None:
        client, calls = self._stub_client()
        family, environment = self._stub_family_and_environment()
        scenario = NativeScenario(
            path=Path("development-scenario.json"),
            raw={
                "scenario_id": "development-001",
                "benchmark_split": "development",
                "matched_variants": [{"id": "state-1"}],
            },
        )
        visible = {
            "ok": False,
            "error": "connection_lost_before_confirmation",
        }
        report = run_native_family_agent(
            client,
            family=family,
            scenario=scenario,
            environment=environment,
            prefix={},
            failure_report={
                "variant": "state-1",
                "latest_attempt": {
                    "tool": "submit_document",
                    "arguments": {"doctype": "Job Card", "name": "JC-1"},
                    "result": visible,
                },
            },
            max_turns=1,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["surface_failure"], visible)
        self.assertTrue(report["evaluation"]["passed"])

    def test_formal_input_lock_is_verified_before_provider_access(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenario.json"
            credentials = root / "credentials.json"
            prefix = root / "prefix.json"
            failure = root / "failure.json"
            scenario_raw = {
                "schema_version": "1.0",
                "scenario_id": "public-dev-001",
                "domain_id": "forgejo",
                "instance_id": "instance-001",
                "instance_spec_sha256": "e" * 64,
                "family": "test-family",
                "benchmark_split": "public_dev",
                "benchmark_tier": "hard",
                "matched_variants": [{"id": "state-1"}],
            }
            scenario_path.write_text(
                json.dumps(scenario_raw),
                encoding="utf-8",
            )
            credentials.write_text("{}", encoding="utf-8")
            prefix.write_text(
                json.dumps({"scenario_id": "public-dev-001"}),
                encoding="utf-8",
            )
            failure.write_text(
                json.dumps(
                    {
                        "scenario_id": "public-dev-001",
                        "variant": "state-1",
                        "visible_failure": {"error": "connection lost"},
                    }
                ),
                encoding="utf-8",
            )
            client, calls = self._stub_client()
            family, environment = self._stub_family_and_environment()
            family.build_environment = lambda _: environment
            with (
                patch.object(
                    NATIVE_FAMILY_REGISTRY,
                    "get",
                    return_value=family,
                ),
                patch(
                    "aftermath_bench.native_model_runner."
                    "verify_formal_input_lock",
                    side_effect=ValueError("formal evidence drift"),
                ) as verifier,
                self.assertRaisesRegex(
                    ValueError,
                    "formal evidence drift",
                ),
            ):
                run_live_native_agent(
                    client,
                    scenario_path=scenario_path,
                    credentials_path=credentials,
                    prefix_path=prefix,
                    failure_report_path=failure,
                    max_turns=1,
                    formal_input_lock_path="data/formal-lock.json",
                )
            self.assertEqual(calls, [])
            verifier.assert_called_once()
            self.assertEqual(
                verifier.call_args.kwargs["prefix_path"],
                prefix,
            )

    def test_verified_formal_input_lock_is_recorded_in_trajectory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenario.json"
            credentials = root / "credentials.json"
            prefix = root / "prefix.json"
            failure = root / "failure.json"
            pre_model = root / "state-1-boundary.json"
            scenario_raw = {
                "schema_version": "1.0",
                "scenario_id": "public-dev-001",
                "domain_id": "forgejo",
                "instance_id": "instance-001",
                "instance_spec_sha256": "e" * 64,
                "family": "test-family",
                "benchmark_split": "public_dev",
                "benchmark_tier": "hard",
                "matched_variants": [{"id": "state-1"}],
            }
            scenario_path.write_text(
                json.dumps(scenario_raw),
                encoding="utf-8",
            )
            credentials.write_text("{}", encoding="utf-8")
            prefix.write_text(
                json.dumps({"scenario_id": "public-dev-001"}),
                encoding="utf-8",
            )
            failure.write_text(
                json.dumps(
                    {
                        "scenario_id": "public-dev-001",
                        "variant": "state-1",
                        "visible_failure": {"error": "connection lost"},
                    }
                ),
                encoding="utf-8",
            )
            pre_model.write_text(
                '{"phase":"boundary","state":"live"}\n',
                encoding="utf-8",
            )
            client, calls = self._stub_client()
            family, environment = self._stub_family_and_environment()
            family.build_environment = lambda _: environment
            verification = SimpleNamespace(
                as_dict=lambda: {
                    "lock_sha256": "a" * 64,
                    "input_envelope_sha256": {
                        "tool_contract": "b" * 64,
                    },
                    "variant_id": "state-1",
                    "boundary_state_sha256": hashlib.sha256(
                        pre_model.read_bytes()
                    ).hexdigest(),
                    "failure_report_sha256": "d" * 64,
                    "prefix_sha256": "f" * 64,
                }
            )
            with (
                patch.object(
                    NATIVE_FAMILY_REGISTRY,
                    "get",
                    return_value=family,
                ),
                patch(
                    "aftermath_bench.native_model_runner."
                    "verify_formal_input_lock",
                    return_value=verification,
                ),
            ):
                report = run_live_native_agent(
                    client,
                    scenario_path=scenario_path,
                    credentials_path=credentials,
                    prefix_path=prefix,
                    failure_report_path=failure,
                    max_turns=1,
                    formal_input_lock_path="data/formal-lock.json",
                    pre_model_boundary_evidence_path=pre_model,
                )
            self.assertEqual(len(calls), 1)
            self.assertEqual(
                report["formal_input_lock"]["variant_id"],
                "state-1",
            )
            self.assertEqual(report["instance_id"], "instance-001")
            self.assertEqual(
                report["instance_spec_sha256"],
                "e" * 64,
            )
            self.assertEqual(
                report["formal_input_lock"]["prefix_sha256"],
                "f" * 64,
            )
            self.assertEqual(
                report["pre_model_boundary_evidence"],
                {
                    "variant_id": "state-1",
                    "source_basename": "state-1-boundary.json",
                    "sha256": hashlib.sha256(
                        pre_model.read_bytes()
                    ).hexdigest(),
                },
            )

    def test_drifted_pre_model_boundary_is_rejected_before_provider(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenario.json"
            credentials = root / "credentials.json"
            prefix = root / "prefix.json"
            failure = root / "failure.json"
            pre_model = root / "state-1-boundary.json"
            scenario_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "scenario_id": "public-dev-001",
                        "domain_id": "forgejo",
                        "instance_id": "instance-001",
                        "instance_spec_sha256": "e" * 64,
                        "family": "test-family",
                        "benchmark_split": "public_dev",
                        "benchmark_tier": "hard",
                        "matched_variants": [{"id": "state-1"}],
                    }
                ),
                encoding="utf-8",
            )
            credentials.write_text("{}", encoding="utf-8")
            prefix.write_text(
                json.dumps({"scenario_id": "public-dev-001"}),
                encoding="utf-8",
            )
            failure.write_text(
                json.dumps(
                    {
                        "scenario_id": "public-dev-001",
                        "variant": "state-1",
                        "visible_failure": {"error": "connection lost"},
                    }
                ),
                encoding="utf-8",
            )
            pre_model.write_text('{"state":"drifted"}\n', encoding="utf-8")
            client, calls = self._stub_client()
            family, environment = self._stub_family_and_environment()
            family.build_environment = lambda _: environment
            verification = SimpleNamespace(
                as_dict=lambda: {
                    "lock_sha256": "a" * 64,
                    "input_envelope_sha256": {
                        "tool_contract": "b" * 64,
                    },
                    "variant_id": "state-1",
                    "boundary_state_sha256": "c" * 64,
                    "failure_report_sha256": "d" * 64,
                    "prefix_sha256": "f" * 64,
                }
            )
            with (
                patch.object(
                    NATIVE_FAMILY_REGISTRY,
                    "get",
                    return_value=family,
                ),
                patch(
                    "aftermath_bench.native_model_runner."
                    "verify_formal_input_lock",
                    return_value=verification,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "does not match the formal input lock",
                ),
            ):
                run_live_native_agent(
                    client,
                    scenario_path=scenario_path,
                    credentials_path=credentials,
                    prefix_path=prefix,
                    failure_report_path=failure,
                    max_turns=1,
                    formal_input_lock_path="data/formal-lock.json",
                    pre_model_boundary_evidence_path=pre_model,
                )
            self.assertEqual(calls, [])
            verification = SimpleNamespace(
                as_dict=lambda: {
                    "lock_sha256": "a" * 64,
                    "input_envelope_sha256": {
                        "tool_contract": "b" * 64,
                    },
                    "variant_id": "state-1",
                    "boundary_state_sha256": "c" * 64,
                    "failure_report_sha256": "d" * 64,
                    "prefix_sha256": "f" * 64,
                }
            )
            with (
                patch.object(
                    NATIVE_FAMILY_REGISTRY,
                    "get",
                    return_value=family,
                ),
                patch(
                    "aftermath_bench.native_model_runner."
                    "verify_formal_input_lock",
                    return_value=verification,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "requires --pre-model-boundary-evidence",
                ),
            ):
                run_live_native_agent(
                    client,
                    scenario_path=scenario_path,
                    credentials_path=credentials,
                    prefix_path=prefix,
                    failure_report_path=failure,
                    max_turns=1,
                    formal_input_lock_path="data/formal-lock.json",
                )
            self.assertEqual(calls, [])

    def test_pre_model_boundary_requires_formal_input_lock(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenario.json"
            credentials = root / "credentials.json"
            prefix = root / "prefix.json"
            failure = root / "failure.json"
            pre_model = root / "state-1-boundary.json"
            scenario_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "scenario_id": "public-dev-001",
                        "domain_id": "forgejo",
                        "instance_id": "instance-001",
                        "instance_spec_sha256": "e" * 64,
                        "family": "test-family",
                        "benchmark_split": "public_dev",
                        "benchmark_tier": "hard",
                        "matched_variants": [{"id": "state-1"}],
                    }
                ),
                encoding="utf-8",
            )
            credentials.write_text("{}", encoding="utf-8")
            prefix.write_text(
                json.dumps({"scenario_id": "public-dev-001"}),
                encoding="utf-8",
            )
            failure.write_text(
                json.dumps(
                    {
                        "scenario_id": "public-dev-001",
                        "variant": "state-1",
                        "visible_failure": {"error": "connection lost"},
                    }
                ),
                encoding="utf-8",
            )
            pre_model.write_text('{"state":"live"}\n', encoding="utf-8")
            client, calls = self._stub_client()
            family, environment = self._stub_family_and_environment()
            family.build_environment = lambda _: environment
            with (
                patch.object(
                    NATIVE_FAMILY_REGISTRY,
                    "get",
                    return_value=family,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "requires --formal-input-lock",
                ),
            ):
                run_live_native_agent(
                    client,
                    scenario_path=scenario_path,
                    credentials_path=credentials,
                    prefix_path=prefix,
                    failure_report_path=failure,
                    max_turns=1,
                    pre_model_boundary_evidence_path=pre_model,
                )
            self.assertEqual(calls, [])

    def test_locked_hidden_family_run_may_access_provider(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenario.json"
            freeze = root / "freeze.json"
            ledger = root / "usage-ledger.json"
            scenario_raw = {
                "scenario_id": "hidden-001",
                "instance_spec_sha256": "instance-spec-sha",
                "benchmark_split": "hidden_test",
                "benchmark_tier": "hard",
                "evaluation_status": {"hidden_test_eligible": True},
                "matched_variants": [{"id": "state-1"}],
            }
            scenario_path.write_text(
                json.dumps(scenario_raw),
                encoding="utf-8",
            )
            freeze.write_text(
                json.dumps(
                    {
                        "scenario_id": "hidden-001",
                        "status": "active",
                        "public_commitment_sha256": "commitment",
                        "scenario_sha256": file_sha256(scenario_path),
                        "instance_spec_semantic_sha256": "instance-spec-sha",
                    }
                ),
                encoding="utf-8",
            )
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={"public_commitment_sha256": "commitment"},
            )
            session = begin_hidden_test_evaluation(
                scenario_path=scenario_path,
                freeze_path=freeze,
                usage_ledger_path=ledger,
                evaluation_id="eval-001",
                provider="openai-compatible",
                model="test-model",
                execution_control=False,
            )
            client, calls = self._stub_client()
            family, environment = self._stub_family_and_environment()
            report = run_native_family_agent(
                client,
                family=family,
                scenario=NativeScenario(
                    path=scenario_path,
                    raw=scenario_raw,
                ),
                environment=environment,
                prefix={},
                failure_report={
                    "variant": "state-1",
                    "visible_failure": {"error": "connection lost"},
                },
                max_turns=1,
                hidden_evaluation_session=session,
                hidden_freeze_path=freeze,
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            report["hidden_evaluation"]["evaluation_id"],
            "eval-001",
        )

    def test_live_hidden_runner_locks_and_finalizes_the_ledger(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario_path = root / "scenario.json"
            credentials = root / "credentials.json"
            prefix = root / "prefix.json"
            failure = root / "failure.json"
            freeze = root / "freeze.json"
            ledger = root / "usage-ledger.json"
            output = root / "trajectory.json"
            scenario_raw = {
                "scenario_id": "hidden-live-001",
                "family": "test-family",
                "instance_spec_sha256": "instance-spec-sha",
                "benchmark_split": "hidden_test",
                "benchmark_tier": "hard",
                "evaluation_status": {"hidden_test_eligible": True},
                "matched_variants": [{"id": "state-1"}],
            }
            scenario_path.write_text(
                json.dumps(scenario_raw),
                encoding="utf-8",
            )
            credentials.write_text("{}", encoding="utf-8")
            prefix.write_text(
                json.dumps({"scenario_id": "hidden-live-001"}),
                encoding="utf-8",
            )
            failure.write_text(
                json.dumps(
                    {
                        "scenario_id": "hidden-live-001",
                        "variant": "state-1",
                        "visible_failure": {"error": "connection lost"},
                    }
                ),
                encoding="utf-8",
            )
            freeze.write_text(
                json.dumps(
                    {
                        "scenario_id": "hidden-live-001",
                        "status": "active",
                        "public_commitment_sha256": "commitment",
                        "scenario_sha256": file_sha256(scenario_path),
                        "instance_spec_semantic_sha256": "instance-spec-sha",
                    }
                ),
                encoding="utf-8",
            )
            append_usage_event(
                ledger_path=ledger,
                event="frozen",
                details={"public_commitment_sha256": "commitment"},
            )
            client, calls = self._stub_client()
            family, environment = self._stub_family_and_environment()
            family.build_environment = lambda _: environment
            with patch.object(
                NATIVE_FAMILY_REGISTRY,
                "get",
                return_value=family,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "hidden-test runs require",
                ):
                    run_live_native_agent(
                        client,
                        scenario_path=scenario_path,
                        credentials_path=credentials,
                        prefix_path=prefix,
                        failure_report_path=failure,
                        max_turns=1,
                    )
                self.assertEqual(calls, [])
                report = run_live_native_agent(
                    client,
                    scenario_path=scenario_path,
                    credentials_path=credentials,
                    prefix_path=prefix,
                    failure_report_path=failure,
                    max_turns=1,
                    output_path=output,
                    hidden_freeze_path=freeze,
                    hidden_usage_ledger_path=ledger,
                    hidden_evaluation_id="evaluation-001",
                    hidden_finalize=True,
                )
            events = json.loads(ledger.read_text(encoding="utf-8"))["events"]
            archived = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [item["event"] for item in events],
            ["frozen", "evaluation_locked", "consumed"],
        )
        self.assertEqual(
            archived["hidden_evaluation"]["consumed_event_sha256"],
            report["hidden_evaluation"]["consumed_event_sha256"],
        )

    def test_execution_control_supplies_scope_but_not_hidden_state(self) -> None:
        message = native_initial_message(
            scenario=self.scenario,
            prefix={
                "purchase_return": "PR-RET-1",
                "trace": [],
            },
            failure_report={
                "visible_failure": {
                    "ok": False,
                    "error": "connection_lost_before_confirmation",
                }
            },
            execution_control=True,
        )
        self.assertIn("correct recovery scope is supplied", message)
        self.assertIn("shared Payment Entry", message)
        self.assertIn("Search the Purchase Invoices", message)
        self.assertIn("never create a second", message)
        for variant in self.scenario.variants:
            self.assertNotIn(variant, message)

    def test_success_is_not_given_a_failure_attribution(self) -> None:
        diagnostics = _diagnose(
            turns=[],
            evaluation=SimpleNamespace(
                passed=True,
                components={
                    "goal_completion": True,
                    "repair_completeness": True,
                    "preservation": True,
                    "protocol_safety": True,
                },
            ),
            failure_report={
                "failure_boundary_evidence": {
                    "purchase_return": {"docstatus": 0}
                }
            },
            prefix={"purchase_return": "PR-RET-1"},
        )
        self.assertIsNone(diagnostics["primary_error"])

    @staticmethod
    def _failed_protocol_evaluation():
        return SimpleNamespace(
            passed=False,
            checks={"no_duplicate_replacement_invoice": False},
            components={
                "goal_completion": True,
                "repair_completeness": True,
                "preservation": True,
                "protocol_safety": False,
            },
        )

    def test_missing_linked_invoice_query_is_investigation_failure(
        self,
    ) -> None:
        diagnostics = _diagnose(
            turns=[
                {
                    "tool_calls": [
                        {
                            "name": "create_purchase_invoice_from_receipt",
                            "arguments": {
                                "purchase_receipt": "PR-REPLACEMENT"
                            },
                        }
                    ],
                    "tool_results": [],
                }
            ],
            evaluation=self._failed_protocol_evaluation(),
            failure_report={
                "failure_boundary_evidence": {
                    "purchase_return": {"docstatus": 1},
                    "replacement_invoices": [
                        {"name": "PINV-EXISTING", "docstatus": 0}
                    ],
                }
            },
            prefix={
                "purchase_return": "PR-RETURN",
                "replacement_purchase_receipt": "PR-REPLACEMENT",
            },
        )
        self.assertEqual(
            diagnostics["primary_error"],
            "investigation_failure",
        )
        self.assertTrue(
            diagnostics[
                "created_invoice_without_linked_invoice_investigation"
            ]
        )

    def test_duplicate_after_query_is_scope_failure(self) -> None:
        diagnostics = _diagnose(
            turns=[
                {
                    "tool_calls": [
                        {
                            "name": "list_documents",
                            "arguments": {
                                "doctype": "Purchase Invoice",
                                "filters": None,
                            },
                        },
                        {
                            "name": "get_external_delivery",
                            "arguments": {"reference": "PR-RETURN"},
                        },
                        {
                            "name": "find_background_jobs",
                            "arguments": {"reference": "PR-RETURN"},
                        },
                        {
                            "name": "create_purchase_invoice_from_receipt",
                            "arguments": {
                                "purchase_receipt": "PR-REPLACEMENT"
                            },
                        },
                    ],
                    "tool_results": [],
                }
            ],
            evaluation=self._failed_protocol_evaluation(),
            failure_report={
                "failure_boundary_evidence": {
                    "purchase_return": {"docstatus": 1},
                    "replacement_invoices": [
                        {"name": "PINV-EXISTING", "docstatus": 0}
                    ],
                }
            },
            prefix={
                "purchase_return": "PR-RETURN",
                "replacement_purchase_receipt": "PR-REPLACEMENT",
            },
        )
        self.assertEqual(diagnostics["primary_error"], "scope_failure")

    def test_one_hop_invoice_query_counts_as_linked_investigation(self) -> None:
        diagnostics = _diagnose(
            turns=[
                {
                    "tool_calls": [
                        {
                            "name": "list_related_documents",
                            "arguments": {
                                "source_doctype": "Purchase Receipt",
                                "source_name": "PR-REPLACEMENT",
                                "target_doctype": "Purchase Invoice",
                            },
                        },
                        {
                            "name": "find_background_jobs",
                            "arguments": {"reference": "PR-RETURN"},
                        },
                        {
                            "name": "get_external_delivery",
                            "arguments": {"reference": "PR-RETURN"},
                        },
                        {
                            "name": "create_purchase_invoice_from_receipt",
                            "arguments": {
                                "purchase_receipt": "PR-REPLACEMENT"
                            },
                        },
                    ],
                    "tool_results": [],
                }
            ],
            evaluation=self._failed_protocol_evaluation(),
            failure_report={
                "failure_boundary_evidence": {
                    "purchase_return": {"docstatus": 1},
                    "replacement_invoices": [
                        {"name": "PINV-EXISTING", "docstatus": 0}
                    ],
                }
            },
            prefix={
                "purchase_return": "PR-RETURN",
                "replacement_purchase_receipt": "PR-REPLACEMENT",
            },
        )
        self.assertFalse(
            diagnostics[
                "created_invoice_without_linked_invoice_investigation"
            ]
        )
        self.assertEqual(diagnostics["primary_error"], "scope_failure")


if __name__ == "__main__":
    unittest.main()
