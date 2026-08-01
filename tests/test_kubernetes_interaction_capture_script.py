from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aftermath_bench.schema import repository_root


def _module():
    path = (
        repository_root()
        / "scripts"
        / "capture_kubernetes_interaction_state_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("capture_k8s_evidence", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Kubernetes evidence capture script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KubernetesInteractionCaptureScriptTests(unittest.TestCase):
    def test_formal_boundary_capture_binds_reset_failure_and_bundle(self) -> None:
        module = _module()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix_path = root / "prefix.json"
            bundle_path = root / "bundle.json"
            reset_path = root / "reset.json"
            failure_path = root / "failure.json"
            pre_snapshot_path = root / "pre-snapshot.json"
            state = {"boundary_facts": {"schema_epoch": "8"}}
            native = {
                "scenario_id": "scenario",
                "variant_id": "state_01",
                "normalization_contract": "contract",
                "state": state,
                "state_sha256": module._state_sha256(state),
            }

            def write(path: Path, payload: dict) -> None:
                path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            write(prefix_path, {"scenario_id": "scenario", "trace": []})
            write(bundle_path, {"schema_version": "1.0"})
            write(
                reset_path,
                {
                    "scenario_id": "scenario",
                    "variant_id": "state_01",
                    "phase": "reset",
                },
            )
            write(
                failure_path,
                {
                    "scenario_id": "scenario",
                    "variant": "state_01",
                    "surface_result": "connection lost",
                    "visible_failure": {"ok": False, "error": "connection lost"},
                    "passed": True,
                },
            )
            write(pre_snapshot_path, native)
            capture = module._formal_capture(
                native=native,
                phase="boundary",
                variant="state_01",
                prefix_path=prefix_path,
                bundle_manifest_path=bundle_path,
                reset_evidence_path=reset_path,
                failure_report_path=failure_path,
                pre_snapshot_path=pre_snapshot_path,
            )
            self.assertEqual(capture["phase"], "boundary")
            self.assertTrue(capture["boundary_validation_passed"])
            self.assertEqual(capture["state"], state)
            self.assertEqual(
                capture["reset_evidence_file_sha256"],
                module._sha256(reset_path),
            )
            self.assertEqual(
                capture["pre_snapshot_state_file_sha256"],
                module._sha256(pre_snapshot_path),
            )

    def test_formal_capture_rejects_restored_state_drift(self) -> None:
        module = _module()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prefix_path = root / "prefix.json"
            bundle_path = root / "bundle.json"
            pre_snapshot_path = root / "pre-snapshot.json"
            prefix_path.write_text(
                json.dumps({"scenario_id": "scenario"}),
                encoding="utf-8",
            )
            bundle_path.write_text("{}", encoding="utf-8")
            pre_snapshot_path.write_text(
                json.dumps({"state": {"uid": "before"}}),
                encoding="utf-8",
            )
            state = {"uid": "after"}
            native = {
                "scenario_id": "scenario",
                "normalization_contract": "contract",
                "state": state,
                "state_sha256": module._state_sha256(state),
            }
            with self.assertRaisesRegex(ValueError, "differs"):
                module._formal_capture(
                    native=native,
                    phase="reset",
                    variant="state_01",
                    prefix_path=prefix_path,
                    bundle_manifest_path=bundle_path,
                    reset_evidence_path=None,
                    failure_report_path=None,
                    pre_snapshot_path=pre_snapshot_path,
                )

    def test_waits_for_byte_exact_boundary_after_transient_drift(self) -> None:
        module = _module()
        expected_payload = {
            "scenario_id": "scenario",
            "variant_id": "state_01",
            "state": {"uid": "original"},
        }
        expected = module._encoded(expected_payload)
        drifted = expected_payload | {"state": {"uid": "different"}}
        with (
            patch.object(
                module,
                "build_interaction_boundary_evidence",
                side_effect=[drifted, expected_payload],
            ) as capture,
            patch.object(module.time, "sleep") as sleep,
        ):
            payload, encoded = module._capture_until_exact(
                api=object(),
                variant="state_01",
                expected=expected,
                wait_seconds=1,
            )
        self.assertEqual(payload, expected_payload)
        self.assertEqual(encoded, expected)
        self.assertEqual(capture.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_rejects_boundary_that_never_becomes_exact(self) -> None:
        module = _module()
        expected = module._encoded({"state": {"uid": "original"}})
        with (
            patch.object(
                module,
                "build_interaction_boundary_evidence",
                return_value={"state": {"uid": "different"}},
            ),
            patch.object(module.time, "sleep"),
            self.assertRaisesRegex(RuntimeError, "differs from expected"),
        ):
            module._capture_until_exact(
                api=object(),
                variant="state_01",
                expected=expected,
                wait_seconds=1,
            )


if __name__ == "__main__":
    unittest.main()
