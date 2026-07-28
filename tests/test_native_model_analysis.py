import json
import tempfile
import unittest
from pathlib import Path

from scripts.analyze_native_model_runs import analyze


class NativeModelAnalysisTest(unittest.TestCase):
    def test_derives_missing_investigation_before_duplicate_create(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "run.json").write_text(
                json.dumps(
                    {
                        "scenario_id": "hard-1",
                        "variant": "database_committed_response_lost",
                        "stop_reason": "model_stopped",
                        "turns": [
                            {
                                "tool_calls": [
                                    {
                                        "name": "get_document",
                                        "arguments": {
                                            "doctype": "Purchase Receipt",
                                            "name": "PR-1",
                                        },
                                    },
                                    {
                                        "name": (
                                            "create_purchase_invoice_"
                                            "from_receipt"
                                        ),
                                        "arguments": {
                                            "purchase_receipt": "PR-2"
                                        },
                                    },
                                ]
                            }
                        ],
                        "evaluation": {
                            "passed": False,
                            "components": {
                                "goal_completion": True,
                                "repair_completeness": True,
                                "preservation": True,
                                "protocol_safety": False,
                            },
                            "checks": {
                                "no_duplicate_replacement_invoice": False
                            },
                        },
                        "trajectory_diagnostics": {
                            "primary_error": "scope_failure",
                            "tool_error_count": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = analyze(root)
        self.assertEqual(
            result["derived_failure_pattern_counts"],
            {"investigation_failure": 1},
        )
        self.assertEqual(
            result["complete_but_protocol_unsafe_count"],
            1,
        )
        self.assertEqual(
            result["created_invoice_without_prior_list_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
