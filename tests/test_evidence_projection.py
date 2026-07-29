from __future__ import annotations

import unittest

from aftermath_bench.evidence_replay import (
    project_evidence,
    select_values,
)


class EvidenceProjectionTest(unittest.TestCase):
    def test_projection_keeps_only_replayed_fields(self) -> None:
        evidence = {
            "invoice": {
                "name": "INV-1",
                "items": [
                    {
                        "purchase_receipt": "PR-1",
                        "description": "large unused field",
                    },
                    {
                        "purchase_receipt": "PR-2",
                        "description": "another unused field",
                    },
                ],
                "unused": {"large": True},
            }
        }
        projected = project_evidence(
            evidence,
            ("invoice.items.*.purchase_receipt", "invoice.name"),
        )
        self.assertEqual(
            select_values(
                projected,
                "invoice.items.*.purchase_receipt",
            ),
            ["PR-1", "PR-2"],
        )
        self.assertEqual(
            projected["invoice"]["name"],
            "INV-1",
        )
        self.assertNotIn("unused", projected["invoice"])
        self.assertNotIn(
            "description",
            projected["invoice"]["items"][0],
        )


if __name__ == "__main__":
    unittest.main()
