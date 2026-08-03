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

    def test_startup_failure_is_retired_without_a_model_score(self) -> None:
        path = (
            ROOT
            / "data"
            / "diagnostics"
            / "erpnext"
            / "hidden-run-30790567945-invalidation.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertFalse(payload["disposition"]["valid_model_evaluation"])
        self.assertFalse(payload["disposition"]["included_in_benchmark_metrics"])
        self.assertFalse(payload["disposition"]["hidden_instance_reusable"])
        audit = payload["redacted_startup_audit"]
        self.assertEqual(
            audit["credential_probe_restore_failure_class"], "erpnext_readiness_timeout"
        )
        self.assertFalse(audit["credential_smoke_present"])
        self.assertEqual(audit["attempt_log_count"], 0)
        self.assertEqual(audit["trajectory_count"], 0)
        regression = payload["remediation"]["cross_run_regression"]
        self.assertTrue(regression["source_stack_destroyed_before_restore"])
        self.assertTrue(regression["old_token_authenticated_after_restore"])

    def test_post_model_serialization_failure_is_not_a_model_score(self) -> None:
        path = (
            ROOT
            / "data"
            / "diagnostics"
            / "erpnext"
            / "hidden-run-30797882168-invalidation.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        disposition = payload["disposition"]
        self.assertFalse(disposition["valid_model_evaluation"])
        self.assertFalse(disposition["included_in_benchmark_metrics"])
        self.assertFalse(disposition["hidden_instance_reusable"])
        audit = payload["redacted_audit"]
        self.assertEqual(audit["attempt_log_count"], 8)
        self.assertEqual(audit["trajectory_count"], 0)
        self.assertEqual(audit["safe_key_error_counts"], {"visible_failure": 7})
        self.assertEqual(
            payload["remediation"]["fix_commit"],
            "48298fe46e3eff9cdfadd5d2511e0ac8ab354037",
        )
        self.assertFalse(payload["raw_hidden_content_published"])
        self.assertFalse(payload["raw_model_logs_published"])


if __name__ == "__main__":
    unittest.main()
