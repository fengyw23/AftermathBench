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
                root
                / "runtime"
                / "bundle-manifests"
                / f"{variant}.json",
                {
                    "schema_version": "1.0",
                    "capture_mode": (
                        "etcd_snapshot_and_quiesced_registry_sqlite"
                    ),
                    "cluster_name": "test-cluster",
                    "node_image": "kindest/node:test@sha256:" + "a" * 64,
                    "files": {
                        "etcd": {
                            "path": "etcd.snapshot.db",
                            "bytes": 100,
                            "sha256": (
                                f"{int(variant[-2:]):064x}"
                            ),
                        },
                        "external_registry": {
                            "path": "webhook-sink.sqlite3",
                            "bytes": 50,
                            "sha256": "f" * 64,
                        },
                    },
                },
            )
            canonical = {
                "scenario_id": SCENARIO_ID,
                "variant_id": variant,
                "state_sha256": f"sha-{variant}",
            }
            _write(
                root
                / "runtime"
                / "state-evidence"
                / f"{variant}-boundary.json",
                canonical,
            )
            _write(
                root
                / "runtime"
                / "state-evidence"
                / f"{variant}-reference-start.json",
                canonical,
            )
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
                    root
                    / "baselines"
                    / "pre-state"
                    / f"{baseline}-{variant}-boundary.json",
                    {
                        "scenario_id": SCENARIO_ID,
                        "variant_id": variant,
                        "state_sha256": f"sha-{variant}",
                    },
                )
                _write(
                    root
                    / "baselines"
                    / "pre-state"
                    / f"{baseline}-{variant}.json",
                    {
                        "scenario_id": SCENARIO_ID,
                        "variant_id": variant,
                        "state_sha256": f"sha-{variant}",
                    },
                )
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
        self.assertEqual(report["native_bundle_manifest_count"], 13)
        self.assertEqual(report["fixed_policy_report_count"], 117)
        self.assertEqual(report["exact_replay_comparison_count"], 130)

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

    def test_rejects_policy_execution_from_a_different_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._fixture(root)
            path = (
                root
                / "baselines"
                / "pre-state"
                / f"{INTERACTION_BASELINES[0]}-"
                f"{KUBERNETES_INTERACTION_VARIANTS[0]}.json"
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["state_sha256"] = "different-boundary"
            _write(path, payload)
            report = _verifier_module().verify_public_dev_admission(root)
        self.assertFalse(report["passed"])
        self.assertFalse(
            report["checks"][
                "fixed_policies_start_from_byte_locked_native_boundaries"
            ]
        )


if __name__ == "__main__":
    unittest.main()
