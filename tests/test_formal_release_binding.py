from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.formal_release_binding import (
    FormalReleaseBindingError,
    generate_formal_release_binding,
)


class FormalReleaseBindingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).parents[1]
        cls.scenario = (
            cls.root
            / "data"
            / "scenarios"
            / "erpnext-sales-return-public-dev-001-r1"
            / "scenario.json"
        )
        cls.declarations = (
            cls.root
            / "data"
            / "evidence"
            / "formal"
            / "aftermathbench-2026.08-r1"
            / "erpnext"
            / "erpnext-sales-return-exchange-reconciliation"
            / "dev-001"
            / "completion"
            / "declarations.json"
        )

    def test_reproduces_the_current_formal_erpnext_release_binding(self) -> None:
        generated = generate_formal_release_binding(
            root=self.root,
            scenario_path=self.scenario,
            declarations_path=self.declarations,
        )
        manifest = json.loads(
            (self.root / "data" / "release_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        expected = next(
            binding
            for binding in manifest["scenario_bindings"]
            if binding["quality_role"] == "release_slot"
        )
        self.assertEqual(generated, expected)

    def test_rejects_declaration_identity_drift_before_binding(self) -> None:
        payload = json.loads(self.declarations.read_text(encoding="utf-8"))
        payload["scenario_id"] = "different-scenario"
        with tempfile.TemporaryDirectory(
            dir=self.root / "data",
            prefix="formal-binding-test-",
        ) as temporary:
            path = Path(temporary) / "declarations.json"
            path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                FormalReleaseBindingError,
                "do not match the active scenario",
            ):
                generate_formal_release_binding(
                    root=self.root,
                    scenario_path=self.scenario,
                    declarations_path=path,
                )


if __name__ == "__main__":
    unittest.main()
