from __future__ import annotations

import unittest

from aftermath_bench.native_formal_spec import (
    CompletionEvidenceSources,
    EvaluatorContractSources,
    FormalSource,
    InputEvidenceSources,
    NativeFormalSpecError,
    PublicToolContract,
    ToolContractSources,
    VariantCompletionEvidence,
    VariantInputEvidence,
    build_completion_roles,
    build_evaluator_role,
    build_input_evidence_roles,
    build_tool_contract_role,
    empty_completion_roles,
)
from aftermath_bench.release_manifest import TRUSTED_FORMAL_EVALUATORS


OUTPUT = "data/evidence/formal/release/domain/family/dev-001"


class NativeFormalSpecTest(unittest.TestCase):
    def test_second_native_domain_has_a_trusted_evaluator(self) -> None:
        self.assertIn(
            "erpnext-sales-return-exchange-reconciliation",
            TRUSTED_FORMAL_EVALUATORS,
        )

    def test_domain_neutral_contract_builds_all_seven_roles(self) -> None:
        tool = build_tool_contract_role(
            output=OUTPUT,
            sources=ToolContractSources(
                definition=FormalSource(
                    "src/domain/family.py",
                    "sources/family.py",
                ),
                implementation=FormalSource(
                    "src/domain/runtime.py",
                    "sources/runtime.py",
                ),
                implementation_dependencies=(
                    FormalSource(
                        "src/domain/api.py",
                        "sources/api.py",
                    ),
                ),
                runtime_revision="revision-1",
                runtime_verification=FormalSource(
                    "evidence/source-verification.json",
                    "native-runtime/source-verification.json",
                ),
                runtime_sources=(
                    FormalSource(
                        "runtime/runtime.lock.json",
                        "native-runtime/01-runtime.lock.json",
                    ),
                ),
                tools=(
                    PublicToolContract(
                        name="get_record",
                        description="Read one authoritative record.",
                        input_schema={
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                        implementation_symbol="Environment.invoke",
                    ),
                ),
            ),
        )
        evaluator = build_evaluator_role(
            output=OUTPUT,
            sources=EvaluatorContractSources(
                implementation=FormalSource(
                    "src/domain/evaluator.py",
                    "sources/evaluator.py",
                ),
                implementation_symbol="evaluate",
                check_ids=("goal", "preservation"),
                scored_state_fields=("records", "events"),
            ),
        )
        inputs = build_input_evidence_roles(
            output=OUTPUT,
            sources=InputEvidenceSources(
                operation="submit the interrupted native document",
                prefix_source_path="native/prefix.json",
                runtime_manifest_source_path="native/files.json",
                runtime_revision="revision-1",
                boundary_verification_source_path=(
                    "evidence/source-verification.json"
                ),
                boundary_contract_sources=(
                    FormalSource(
                        "scripts/run_boundary.py",
                        "native-boundary/01-run_boundary.py",
                    ),
                ),
                reset_capture_manifest_sources=(
                    "native/reset-bundle.json",
                ),
                boundary_capture_manifest_sources=(
                    "native/boundary-a-bundle.json",
                    "native/boundary-b-bundle.json",
                ),
                variants=(
                    self._input_variant("a"),
                    self._input_variant("b"),
                ),
            ),
        )
        completion = build_completion_roles(
            output=OUTPUT,
            input_variant_ids=("a", "b"),
            sources=CompletionEvidenceSources(
                control_manifest_source_path="control/files.json",
                model_input_lock_source_path=(
                    f"{OUTPUT}/formal-input-lock.json"
                ),
                variants=(
                    self._completion_variant("a", passed=True),
                    self._completion_variant("b", passed=False),
                ),
            ),
        )
        roles = {
            "tool_contract": tool,
            "evaluator": evaluator,
            **inputs,
            **completion,
        }

        self.assertEqual(
            set(roles),
            {
                "tool_contract",
                "evaluator",
                "reset_evidence",
                "boundary_bundle",
                "reference_bundle",
                "raw_run_archive",
                "execution_control",
            },
        )
        self.assertEqual(
            roles["tool_contract"]["primary_payload"]["tool_count"],
            1,
        )
        self.assertEqual(
            len(roles["boundary_bundle"]["primary_payload"]["variants"]),
            2,
        )
        control = roles["execution_control"]["primary_payload"]
        self.assertEqual(control["passed_runs"], 1)
        self.assertEqual(control["task_pass_rate"], 0.5)
        self.assertEqual(
            set(empty_completion_roles()),
            {"raw_run_archive", "execution_control"},
        )

    def test_rejects_domain_adapter_path_escape(self) -> None:
        with self.assertRaisesRegex(
            NativeFormalSpecError,
            "canonical relative POSIX path",
        ):
            build_evaluator_role(
                output=OUTPUT,
                sources=EvaluatorContractSources(
                    implementation=FormalSource(
                        "../private/evaluator.py",
                        "sources/evaluator.py",
                    ),
                    implementation_symbol="evaluate",
                    check_ids=("goal",),
                    scored_state_fields=("records",),
                ),
            )

    def test_rejects_duplicate_or_reordered_completion_variants(self) -> None:
        duplicated = InputEvidenceSources(
            operation="submit",
            prefix_source_path="native/prefix.json",
            runtime_manifest_source_path="native/files.json",
            runtime_revision="revision-1",
            boundary_verification_source_path="native/verification.json",
            boundary_contract_sources=(),
            reset_capture_manifest_sources=(),
            boundary_capture_manifest_sources=(),
            variants=(
                self._input_variant("same"),
                self._input_variant("same"),
            ),
        )
        with self.assertRaisesRegex(
            NativeFormalSpecError,
            "non-empty and unique",
        ):
            build_input_evidence_roles(
                output=OUTPUT,
                sources=duplicated,
            )

        with self.assertRaisesRegex(
            NativeFormalSpecError,
            "exactly match input variants in order",
        ):
            build_completion_roles(
                output=OUTPUT,
                input_variant_ids=("a", "b"),
                sources=CompletionEvidenceSources(
                    control_manifest_source_path="control/files.json",
                    model_input_lock_source_path=(
                        f"{OUTPUT}/formal-input-lock.json"
                    ),
                    variants=(
                        self._completion_variant("b", passed=True),
                        self._completion_variant("a", passed=True),
                    ),
                ),
            )

    @staticmethod
    def _input_variant(variant_id: str) -> VariantInputEvidence:
        return VariantInputEvidence(
            variant_id=variant_id,
            reset_source_path=f"native/{variant_id}-reset.json",
            boundary_state_source_path=(
                f"native/{variant_id}-boundary-state.json"
            ),
            raw_failure_report_source_path=(
                f"native/{variant_id}-failure.json"
            ),
            reference_start_state_source_path=(
                f"native/{variant_id}-reference-start.json"
            ),
            raw_reference_report_source_path=(
                f"native/{variant_id}-reference.json"
            ),
        )

    @staticmethod
    def _completion_variant(
        variant_id: str,
        *,
        passed: bool,
    ) -> VariantCompletionEvidence:
        return VariantCompletionEvidence(
            variant_id=variant_id,
            run_id=f"control-{variant_id}",
            trajectory_source_path=f"control/{variant_id}.json",
            pre_model_boundary_source_path=(
                f"control/{variant_id}-pre-model.json"
            ),
            passed=passed,
        )


if __name__ == "__main__":
    unittest.main()
