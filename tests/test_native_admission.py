import unittest

from aftermath_bench.native_admission import validate_native_scenario
from aftermath_bench.native_scenario import (
    load_native_scenario,
    native_scenario_paths,
)


class NativeAdmissionTest(unittest.TestCase):
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
