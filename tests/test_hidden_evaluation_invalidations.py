from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class HiddenEvaluationInvalidationTests(unittest.TestCase):
    def test_invalidated_run_cannot_be_reported_or_reused(self) -> None:
        path = (
            ROOT
            / "data"
            / "diagnostics"
            / "erpnext"
            / "hidden-run-30786512162-invalidation.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(payload["disposition"]["valid_model_evaluation"])
        self.assertFalse(payload["disposition"]["included_in_benchmark_metrics"])
        self.assertFalse(payload["disposition"]["hidden_instance_reusable"])
        self.assertEqual(payload["redacted_audit"]["trajectory_count"], 0)
        self.assertEqual(
            payload["redacted_audit"]["classification_counts"],
            {"native_authentication_error": 8},
        )
        self.assertFalse(payload["raw_hidden_content_published"])
        self.assertFalse(payload["raw_model_logs_published"])


if __name__ == "__main__":
    unittest.main()
