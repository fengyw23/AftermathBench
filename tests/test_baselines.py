import unittest

from aftermath_bench.baselines import run_itsm_baselines, run_release_baselines


class BaselineTest(unittest.TestCase):
    def test_fixed_heuristics_fail_matched_fault_group(self) -> None:
        report = run_release_baselines()
        self.assertFalse(report["blind_retry"]["matched_group_success"])
        self.assertFalse(report["assume_committed"]["matched_group_success"])
        self.assertFalse(report["query_deployment_only"]["matched_group_success"])
        self.assertTrue(report["investigate_and_repair"]["matched_group_success"])

    def test_itsm_main_record_heuristics_fail_matched_fault_group(self) -> None:
        report = run_itsm_baselines()
        self.assertFalse(report["blind_retry"]["matched_group_success"])
        self.assertFalse(report["assume_committed"]["matched_group_success"])
        self.assertFalse(report["query_incident_only"]["matched_group_success"])
        self.assertTrue(report["investigate_and_repair"]["matched_group_success"])


if __name__ == "__main__":
    unittest.main()
