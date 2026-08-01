from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.integrations.kubernetes_interaction_baselines import (
    INTERACTION_BASELINES,
)
from aftermath_bench.integrations.kubernetes_interaction_prefix import (
    SCENARIO_ID,
)
from aftermath_bench.integrations.kubernetes_interaction_scope import (
    KUBERNETES_INTERACTION_VARIANTS,
)
from aftermath_bench.schema import repository_root


def _verifier_module():
    path = (
        repository_root()
        / "scripts"
        / "verify_kubernetes_interaction_public_dev_admission.py"
    )
    spec = importlib.util.spec_from_file_location("public_dev_verifier", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load public-dev admission verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class KubernetesInteractionPublicDevAdmissionVerifierTests(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        _write(
            root / "runtime-summary.json",
            {
                "scenario_id": SCENARIO_ID,
                "passed": True,
                "variant_count": len(KUBERNETES_INTERACTION_VARIANTS),
                "reference_pass_count": len(KUBERNETES_INTERACTION_VARIANTS),
            },
        )
        for variant in KUBERNETES_INTERACTION_VARIANTS:
            _write(
                root / "runtime" / f"{variant}-reference.json",
                {
                    "scenario_id": SCENARIO_ID,
                    "evaluation": {"passed": True},
                    "control_error": None,
                },
            )
        for baseline in INTERACTION_BASELINES:
            for variant in KUBERNETES_INTERACTION_VARIANTS:
                _write(
                    root / "baselines" / f"{baseline}-{variant}.json",
                    {"scenario_id": SCENARIO_ID},
                )
        _write(
            root / "baselines" / "summary.json",
            {
                "heuristics": [
                    {"name": name} for name in INTERACTION_BASELINES
                ],
                "hard_fixed_policy_gate_passed": True,
                "maximum_heuristic_pass_rate": 0.25,
                "matched_group_solvers": [],
            },
        )
        _write(
            root / "admitted-scenario" / "artifacts" / "admission.json",
            {
                "scenario_id": SCENARIO_ID,
                "passed": True,
                "admitted_tier": "hard",
            },
        )
        _write(
            root / "admitted-scenario" / "scenario.json",
            {
                "scenario_id": SCENARIO_ID,
                "benchmark_tier": "hard",
                "admission_status": "validated",
            },
        )

    def test_accepts_complete_reference_policy_and_admission_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root)
            report = _verifier_module().verify_public_dev_admission(root)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["reference_report_count"], 13)
        self.assertEqual(report["fixed_policy_report_count"], 117)

    def test_rejects_a_fixed_policy_matched_group_solver(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root)
            summary_path = root / "baselines" / "summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["matched_group_solvers"] = ["shortcut"]
            _write(summary_path, summary)
            report = _verifier_module().verify_public_dev_admission(root)
        self.assertFalse(report["passed"])
        self.assertFalse(report["checks"]["fixed_policy_hard_gate_passes"])


if __name__ == "__main__":
    unittest.main()
