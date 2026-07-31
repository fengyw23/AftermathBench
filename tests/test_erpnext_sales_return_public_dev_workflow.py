from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.integrations.erpnext_faults import (
    ERP_NEXT_FAULT_VARIANTS,
)


class ERPNextSalesReturnPublicDevWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = Path(
            ".github/workflows/erpnext-sales-return-public-dev.yml"
        ).read_text(encoding="utf-8")

    def test_fresh_instance_is_checked_before_runtime_build(self) -> None:
        novelty = self.text.index(
            "verify_erpnext_sales_return_instance_novelty.py"
        )
        render = self.text.index(
            "render_erpnext_sales_return_blueprint.py"
        )
        runtime = self.text.index("build_erpnext_runtime.py")
        self.assertLess(novelty, render)
        self.assertLess(render, runtime)
        self.assertIn(
            'cmp "$BLUEPRINT" "$RUN_ROOT/rendered-blueprint.json"',
            self.text,
        )

    def test_every_consumer_starts_from_the_same_exact_boundary(self) -> None:
        capture = self.text[
            self.text.index("Capture four exact boundaries"):
            self.text.index("Execute every fixed policy")
        ]
        baselines = self.text[
            self.text.index("Execute every fixed policy"):
            self.text.index("Admit the active scenario")
        ]
        controls = self.text[
            self.text.index("Run execution controls"):
            self.text.index("Complete and validate")
        ]
        exact = '"$NATIVE_ROOT/bundles/boundary-$variant"'
        self.assertIn(exact, capture)
        self.assertIn(exact, baselines)
        self.assertIn(exact, controls)
        self.assertNotIn(
            "run_erpnext_sales_return_failure.py",
            baselines,
        )
        self.assertNotIn(
            "run_erpnext_sales_return_failure.py",
            controls,
        )

    def test_reset_boundary_and_reference_are_byte_bound(self) -> None:
        section = self.text[
            self.text.index("Capture four exact boundaries"):
            self.text.index("Execute every fixed policy")
        ]
        reset = section.index("--phase reset")
        failure = section.index(
            "run_erpnext_sales_return_failure.py",
            reset,
        )
        snapshot = section.index("snapshot-bundle", failure)
        boundary = section.index("--phase boundary", snapshot)
        restore = section.index("restore-bundle", boundary)
        recapture = section.index(
            "capture_erpnext_sales_return_state_evidence.py",
            restore,
        )
        compare = section.index(
            'cmp "$boundary" "$reference_start"',
            recapture,
        )
        reference = section.index(
            "run_erpnext_sales_return_control.py",
            compare,
        )
        self.assertLess(reset, failure)
        self.assertLess(failure, snapshot)
        self.assertLess(snapshot, boundary)
        self.assertLess(boundary, restore)
        self.assertLess(restore, recapture)
        self.assertLess(recapture, compare)
        self.assertLess(compare, reference)
        self.assertIn("--formal-contract", section)

    def test_input_lock_precedes_provider_secret_and_model(self) -> None:
        input_roles = self.text.index(
            "Freeze the five formal input roles before provider access"
        )
        generator = self.text.index(
            "generate_erpnext_formal_build_spec.py",
            input_roles,
        )
        input_build = self.text.index(
            "build_formal_evidence.py",
            generator,
        )
        control = self.text.index(
            "Run execution controls from the locked exact boundaries"
        )
        secret = self.text.index(
            "AFTERMATH_API_KEY: ${{ secrets.BAILIAN_API_KEY }}",
            control,
        )
        model = self.text.index("run-native-model", secret)
        self.assertLess(input_roles, generator)
        self.assertLess(generator, input_build)
        self.assertLess(input_build, control)
        self.assertLess(control, secret)
        self.assertLess(secret, model)
        self.assertNotIn("BAILIAN_API_KEY", self.text[:control])
        self.assertIn("--formal-input-lock", self.text[model:])
        self.assertIn("--pre-model-boundary-evidence", self.text[model:])

    def test_all_four_variants_and_strict_control_gate_are_bound(self) -> None:
        blueprint = Path(
            "data/scenario_blueprints/"
            "erpnext-sales-return-public-dev-001/scenario.json"
        ).read_text(encoding="utf-8")
        for variant in ERP_NEXT_FAULT_VARIANTS:
            self.assertIn(variant, blueprint)
        self.assertIn('test "${#variants[@]}" -eq 4', self.text)
        self.assertIn("--expected-cases 4", self.text)
        self.assertIn("--minimum-pass-rate 0.8", self.text)
        self.assertIn("--expected-execution-control true", self.text)

    def test_completion_and_public_archive_are_fail_closed(self) -> None:
        control = self.text.index("Run execution controls")
        complete = self.text.index("Complete and validate", control)
        complete_spec = self.text.index(
            "generate_erpnext_formal_build_spec.py",
            complete,
        )
        complete_build = self.text.index(
            "build_formal_evidence.py",
            complete_spec,
        )
        seal = self.text.index(
            "Seal the safe public evidence archive",
            complete_build,
        )
        self.assertLess(control, complete)
        self.assertLess(complete, complete_spec)
        self.assertLess(complete_spec, complete_build)
        self.assertLess(complete_build, seal)
        seal_text = self.text[seal:]
        self.assertIn(
            'test -s "$FORMAL_OUTPUT/completion/declarations.json"',
            seal_text,
        )
        self.assertIn(
            "build_erpnext_public_evidence_archive.py",
            seal_text,
        )
        self.assertIn(
            "--expected-restore-bundle-count 5",
            seal_text,
        )
        self.assertIn("credentials.json", seal_text)


if __name__ == "__main__":
    unittest.main()
