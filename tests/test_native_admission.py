import unittest

from aftermath_bench.native_admission import (
    _reference_evidence_groups,
    validate_native_scenario,
)
from aftermath_bench.native_scenario import (
    load_native_scenario,
    native_scenario_paths,
)


class NativeAdmissionTest(unittest.TestCase):
    def test_domain_specific_evidence_groups_are_tool_driven(self) -> None:
        graph = {
            "evidence_tool_groups": [
                {"id": "objects", "tools": ["get_object", "list_objects"]},
                {"id": "events", "tools": ["list_events"]},
                {"id": "logs", "tools": ["get_job_logs"]},
                {
                    "id": "external",
                    "tools": ["list_external_deliveries"],
                },
            ]
        }
        groups = _reference_evidence_groups(
            {
                "list_objects",
                "list_events",
                "get_job_logs",
                "list_external_deliveries",
            },
            graph,
        )
        self.assertTrue(all(groups.values()))

    def test_payment_pilot_is_truthfully_classified_easy(self) -> None:
        path = next(
            path
            for path in native_scenario_paths()
            if path.parent.name == "erpnext-procurement-payment-001"
        )
        report = validate_native_scenario(load_native_scenario(path))
        self.assertTrue(report.passed, report.failures)
        self.assertEqual(report.requested_tier, "easy")
        self.assertEqual(report.admitted_tier, "easy")
        self.assertFalse(report.checks["minimum_mutations>=4"])
        self.assertFalse(report.checks["no_single_query_is_decisive"])
        self.assertFalse(report.checks["heuristic_pass_rate<0.5"])


if __name__ == "__main__":
    unittest.main()
