from __future__ import annotations

import importlib.util
import unittest
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
        ):
            with self.assertRaisesRegex(RuntimeError, "differs from expected"):
                module._capture_until_exact(
                    api=object(),
                    variant="state_01",
                    expected=expected,
                    wait_seconds=1,
                )


if __name__ == "__main__":
    unittest.main()
