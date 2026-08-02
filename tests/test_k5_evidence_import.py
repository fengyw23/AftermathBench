from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aftermath_bench.k5_evidence_import import (
    K5EvidenceImportError,
    K5EvidenceImportGate,
    build_k5_import_provenance,
    select_k4_artifact_metadata,
    validate_k4_artifact_layout,
    validate_k4_public_summary,
    validate_k4_run_metadata,
)

RUN_ID = 123456
K4_COMMIT = "1" * 40
SOURCE_RUN_ID = 123400
SOURCE_COMMIT = "2" * 40


def _gate_payload() -> dict[str, object]:
    return {
        "schema_version": "1.2",
        "stage": "K5-evidence-import",
        "k4_run_id": RUN_ID,
        "k4_commit": K4_COMMIT,
        "k4_expected_conclusion": "success",
        "k4_artifact": f"kubernetes-execution-control-{RUN_ID}",
        "k4_artifact_digest": "sha256:" + "a" * 64,
        "formal_repair_mode": "none",
        "formal_repair_revision": 1,
        "source_run_id": SOURCE_RUN_ID,
        "source_commit": SOURCE_COMMIT,
        "minimum_pass_rate": 0.8,
    }


def _summary() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "stage": "K4-execution-control",
        "source_run_id": SOURCE_RUN_ID,
        "source_commit": SOURCE_COMMIT,
        "model": "DeepSeek-V4-Pro",
        "expected_cases": 13,
        "minimum_pass_rate": 0.8,
        "completed_runs": 13,
        "task_pass_rate": 12 / 13,
        "matched_group_count": 1,
        "matched_group_success_rate": 0.0,
        "component_pass_rates": {"goal_completion": 12 / 13},
        "failure_type_counts": {"scope_failure": 1},
        "execution_control_counts": {"true": 13},
        "run_error_count": 0,
    }


def _artifact() -> dict[str, object]:
    return {
        "id": 999,
        "name": f"kubernetes-execution-control-{RUN_ID}",
        "expired": False,
        "size_in_bytes": 1024,
        "digest": "sha256:" + "a" * 64,
    }


class K5EvidenceImportTests(unittest.TestCase):
    def test_gate_is_exact_and_exports_only_bound_values(self) -> None:
        gate = K5EvidenceImportGate.from_mapping(_gate_payload())
        self.assertEqual(gate.k4_run_id, RUN_ID)
        self.assertEqual(gate.minimum_pass_rate, 0.8)
        self.assertEqual(
            gate.github_environment()["K4_ARTIFACT"],
            f"kubernetes-execution-control-{RUN_ID}",
        )
        for key, value in (
            ("extra", True),
            ("k4_artifact", "wrong"),
            ("minimum_pass_rate", 0.7),
            ("source_commit", "short"),
        ):
            with self.subTest(key=key):
                payload = _gate_payload()
                payload[key] = value
                with self.assertRaises(K5EvidenceImportError):
                    K5EvidenceImportGate.from_mapping(payload)

    def test_gate_strict_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "gate.json"
            path.write_text(
                json.dumps(_gate_payload())[:-1] + ',"stage":"duplicate"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate JSON"):
                K5EvidenceImportGate.from_path(path)

    def test_run_provenance_binds_exact_declared_workflow_conclusion(self) -> None:
        gate = K5EvidenceImportGate.from_mapping(_gate_payload())
        run = {
            "id": RUN_ID,
            "head_sha": K4_COMMIT,
            "status": "completed",
            "conclusion": "success",
            "path": (
                ".github/workflows/"
                "kubernetes-interaction-execution-control.yml"
            ),
        }
        validate_k4_run_metadata(run, gate=gate)
        for key, value in (
            ("head_sha", "3" * 40),
            ("conclusion", "failure"),
            ("path", ".github/workflows/other.yml"),
        ):
            with self.subTest(key=key):
                drifted = run | {key: value}
                with self.assertRaises(K5EvidenceImportError):
                    validate_k4_run_metadata(drifted, gate=gate)

        recovery_payload = _gate_payload() | {
            "k4_expected_conclusion": "failure",
            "formal_repair_mode": "k4-post-control-formalization-v1",
        }
        recovery_gate = K5EvidenceImportGate.from_mapping(recovery_payload)
        validate_k4_run_metadata(
            run | {"conclusion": "failure"}, gate=recovery_gate
        )

    def test_gate_rejects_unreviewed_failure_or_repair_mode(self) -> None:
        for conclusion, mode in (
            ("failure", "none"),
            ("success", "k4-post-control-formalization-v1"),
            ("failure", "arbitrary-repair"),
        ):
            with self.subTest(conclusion=conclusion, mode=mode):
                payload = _gate_payload() | {
                    "k4_expected_conclusion": conclusion,
                    "formal_repair_mode": mode,
                }
                with self.assertRaises(K5EvidenceImportError):
                    K5EvidenceImportGate.from_mapping(payload)

    def test_artifact_requires_unique_live_nonempty_digest(self) -> None:
        gate = K5EvidenceImportGate.from_mapping(_gate_payload())
        selected = select_k4_artifact_metadata(
            {"artifacts": [_artifact()]}, gate=gate
        )
        self.assertEqual(selected["id"], 999)
        for key, value in (
            ("expired", True),
            ("size_in_bytes", 0),
            ("digest", None),
        ):
            with self.subTest(key=key):
                artifact = _artifact() | {key: value}
                with self.assertRaises(K5EvidenceImportError):
                    select_k4_artifact_metadata(
                        {"artifacts": [artifact]}, gate=gate
                    )
        with self.assertRaisesRegex(K5EvidenceImportError, "not unique"):
            select_k4_artifact_metadata(
                {"artifacts": [_artifact(), _artifact()]}, gate=gate
            )

    def test_summary_rejects_forged_or_nondiscrete_scores(self) -> None:
        gate = K5EvidenceImportGate.from_mapping(_gate_payload())
        validate_k4_public_summary(_summary(), gate=gate)
        for key, value in (
            ("completed_runs", 12),
            ("task_pass_rate", 0.81),
            ("task_pass_rate", 10 / 13),
            ("run_error_count", 1),
            ("execution_control_counts", {"true": 12}),
        ):
            with self.subTest(key=key, value=value):
                summary = _summary() | {key: value}
                with self.assertRaises(K5EvidenceImportError):
                    validate_k4_public_summary(summary, gate=gate)

    def test_layout_requires_exact_roots_and_no_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            generated = root / "generated" / "public-dev-slot-003"
            scenario = root / "scenarios" / "public-dev-slot-003"
            formal = (
                root
                / "evidence"
                / "formal"
                / "aftermathbench-2026.08-r1"
                / "kubernetes"
                / "k8s-constraint-interaction-recovery"
                / "dev-006"
                / "completion"
            )
            generated.mkdir(parents=True)
            scenario.mkdir(parents=True)
            formal.mkdir(parents=True)
            (generated / "k4-public-summary.json").write_text(
                "{}", encoding="utf-8"
            )
            (scenario / "scenario.json").write_text("{}", encoding="utf-8")
            (formal.parent / "formal-input-lock.json").write_text(
                "{}", encoding="utf-8"
            )
            (formal / "declarations.json").write_text("{}", encoding="utf-8")
            paths = validate_k4_artifact_layout(root)
            self.assertEqual(paths["summary"].name, "k4-public-summary.json")
            (root / "unexpected").mkdir()
            with self.assertRaisesRegex(
                K5EvidenceImportError, "unexpected K4 artifact roots"
            ):
                validate_k4_artifact_layout(root)

    def test_layout_can_stage_post_model_formalization_repair(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            generated = root / "generated" / "public-dev-slot-003"
            scenario = root / "scenarios" / "public-dev-slot-003"
            formal = (
                root
                / "evidence"
                / "formal"
                / "aftermathbench-2026.08-r1"
                / "kubernetes"
                / "k8s-constraint-interaction-recovery"
                / "dev-006"
            )
            generated.mkdir(parents=True)
            scenario.mkdir(parents=True)
            formal.mkdir(parents=True)
            (generated / "k4-public-summary.json").write_text(
                "{}", encoding="utf-8"
            )
            (scenario / "scenario.json").write_text("{}", encoding="utf-8")
            (formal / "formal-input-lock.json").write_text(
                "{}", encoding="utf-8"
            )
            paths = validate_k4_artifact_layout(
                root, require_completion=False
            )
            self.assertEqual(paths["input_lock"].name, "formal-input-lock.json")
            self.assertNotIn("declarations", paths)
            with self.assertRaisesRegex(
                K5EvidenceImportError, "declarations"
            ):
                validate_k4_artifact_layout(root)

    def test_provenance_is_normalized_and_hash_bound(self) -> None:
        gate = K5EvidenceImportGate.from_mapping(_gate_payload())
        provenance = build_k5_import_provenance(
            gate=gate,
            artifact=_artifact(),
            import_gate_commit="f" * 40,
        )
        self.assertEqual(provenance["k4_run_id"], RUN_ID)
        self.assertEqual(
            provenance["artifact"]["digest"], "sha256:" + "a" * 64
        )
        self.assertFalse(provenance["formal_repair"]["model_was_rerun"])
        with self.assertRaisesRegex(K5EvidenceImportError, "commit"):
            build_k5_import_provenance(
                gate=gate,
                artifact=_artifact(),
                import_gate_commit="short",
            )


if __name__ == "__main__":
    unittest.main()
