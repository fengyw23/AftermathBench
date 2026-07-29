from __future__ import annotations

import unittest

from scripts.build_native_sales_return_admission import (
    _minimum_distinguishing_signal_count,
)


class NativeSalesAdmissionBuilderTest(unittest.TestCase):
    def test_all_three_authoritative_signals_are_required(self) -> None:
        rows = [
            {
                "signals": {
                    "sales_return": 0,
                    "external_delivery": False,
                    "background_job": False,
                }
            },
            {
                "signals": {
                    "sales_return": 1,
                    "external_delivery": True,
                    "background_job": False,
                }
            },
            {
                "signals": {
                    "sales_return": 1,
                    "external_delivery": False,
                    "background_job": False,
                }
            },
            {
                "signals": {
                    "sales_return": 1,
                    "external_delivery": False,
                    "background_job": True,
                }
            },
        ]
        self.assertEqual(
            _minimum_distinguishing_signal_count(
                rows,
                (
                    "sales_return",
                    "external_delivery",
                    "background_job",
                ),
            ),
            3,
        )


if __name__ == "__main__":
    unittest.main()
