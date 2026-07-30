from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.analyze_kubernetes_interaction_runs import (
    analyze_kubernetes_interaction_runs,
)


class KubernetesInteractionAnalysisTest(unittest.TestCase):
    def test_reports_external_envelope_violation(self) -> None:
        report = {
            "family": "k8s-constraint-interaction-recovery",
            "variant": "state_01",
            "execution_control": True,
            "turns": [{"tool_calls": [{}, {}]}],
            "evaluation": {
                "passed": False,
                "components": {"protocol_safety": False},
                "checks": {"external_event_envelope_exact": False},
                "diagnostics": {
                    "semantic_recovery_direction": "discard_failed_change",
                    "allowed_external_keys": [
                        "release:orders-platform-v1",
                        "audit:recovery:orders-platform-v2",
                    ],
                    "actual_external_keys": [
                        "release:orders-platform-v1",
                        "compensate:prepare:orders-platform-v2",
                        "audit:recovery:orders-platform-v2",
                    ],
                    "protocol_violations": ["unexpected compensation event"],
                },
            },
            "trajectory_diagnostics": {
                "primary_error": "scope_failure",
                "evidence_groups": {"contracts": True, "registry": True},
                "selected_mutations": ["post_external_event"],
            },
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state_01.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            result = analyze_kubernetes_interaction_runs(root)

        self.assertEqual(result["completed_runs"], 1)
        self.assertEqual(result["task_pass_rate"], 0)
        self.assertEqual(
            result["unexpected_external_key_counts"],
            {"compensate:prepare:orders-platform-v2": 1},
        )
        self.assertEqual(
            result["protocol_violation_counts"],
            {"unexpected compensation event": 1},
        )
        self.assertEqual(result["primary_error_counts"], {"scope_failure": 1})


if __name__ == "__main__":
    unittest.main()
