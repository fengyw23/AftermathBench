from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from scripts.rescore_kubernetes_interaction_runs import rescore_reports


class KubernetesInteractionRescoreTest(unittest.TestCase):
    def test_records_changed_evaluator_result(self) -> None:
        report = {
            "family": "k8s-constraint-interaction-recovery",
            "variant": "state_12",
            "final_evidence": {"value": 2},
            "evaluation": {
                "passed": False,
                "failures": [
                    "closure_event_records_observed_facts",
                    "release_obligation_closed",
                ],
            },
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state_12.json").write_text(
                json.dumps(report),
                encoding="utf-8",
            )
            result = rescore_reports(
                root,
                evaluator=lambda _evidence: SimpleNamespace(
                    passed=True,
                    failures=(),
                ),
            )

        self.assertEqual(result["completed_runs"], 1)
        self.assertEqual(result["original_task_pass_rate"], 0.0)
        self.assertEqual(result["rescored_task_pass_rate"], 1.0)
        self.assertEqual(result["changed_run_count"], 1)
        self.assertEqual(result["reports"][0]["path"], "state_12.json")


if __name__ == "__main__":
    unittest.main()
