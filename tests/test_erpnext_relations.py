from __future__ import annotations

import unittest

from aftermath_bench.integrations.erpnext_relations import (
    find_related_documents,
)


class ERPNextRelationTest(unittest.TestCase):
    def test_finds_invoice_through_purchase_receipt_child_link(self) -> None:
        documents = [
            {
                "name": "PINV-1",
                "items": [{"purchase_receipt": "PREC-REPLACEMENT"}],
            },
            {
                "name": "PINV-2",
                "items": [{"purchase_receipt": "PREC-OTHER"}],
            },
        ]
        related = find_related_documents(
            source_doctype="Purchase Receipt",
            source_name="PREC-REPLACEMENT",
            target_doctype="Purchase Invoice",
            documents=documents,
        )
        self.assertEqual(
            [item["document"]["name"] for item in related],
            ["PINV-1"],
        )
        self.assertEqual(
            related[0]["evidence"][0]["matched_paths"],
            ["items[0].purchase_receipt"],
        )

    def test_payment_reference_requires_matching_reference_type(self) -> None:
        documents = [
            {
                "name": "PAY-1",
                "references": [
                    {
                        "reference_doctype": "Purchase Invoice",
                        "reference_name": "PINV-1",
                    }
                ],
            },
            {
                "name": "PAY-2",
                "references": [
                    {
                        "reference_doctype": "Sales Invoice",
                        "reference_name": "PINV-1",
                    }
                ],
            },
        ]
        related = find_related_documents(
            source_doctype="Purchase Invoice",
            source_name="PINV-1",
            target_doctype="Payment Entry",
            documents=documents,
            relation_type="paid_by",
        )
        self.assertEqual(
            [item["document"]["name"] for item in related],
            ["PAY-1"],
        )

    def test_rejects_an_unsupported_relation_instead_of_guessing(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported one-hop relation"):
            find_related_documents(
                source_doctype="Item",
                source_name="ITEM-1",
                target_doctype="Payment Entry",
                documents=[],
            )

    def test_finds_sales_invoice_through_delivery_note_child_link(
        self,
    ) -> None:
        related = find_related_documents(
            source_doctype="Delivery Note",
            source_name="DN-EXCHANGE",
            target_doctype="Sales Invoice",
            documents=[
                {
                    "name": "SINV-1",
                    "items": [{"delivery_note": "DN-EXCHANGE"}],
                },
                {
                    "name": "SINV-2",
                    "items": [{"delivery_note": "DN-OTHER"}],
                },
            ],
        )
        self.assertEqual(
            [item["document"]["name"] for item in related],
            ["SINV-1"],
        )

    def test_sales_payment_requires_sales_reference_type(self) -> None:
        related = find_related_documents(
            source_doctype="Sales Invoice",
            source_name="SINV-1",
            target_doctype="Payment Entry",
            relation_type="paid_by",
            documents=[
                {
                    "name": "PAY-SALES",
                    "references": [
                        {
                            "reference_doctype": "Sales Invoice",
                            "reference_name": "SINV-1",
                        }
                    ],
                },
                {
                    "name": "PAY-PURCHASE",
                    "references": [
                        {
                            "reference_doctype": "Purchase Invoice",
                            "reference_name": "SINV-1",
                        }
                    ],
                },
            ],
        )
        self.assertEqual(
            [item["document"]["name"] for item in related],
            ["PAY-SALES"],
        )


if __name__ == "__main__":
    unittest.main()
