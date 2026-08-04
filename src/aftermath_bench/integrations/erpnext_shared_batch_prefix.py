from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from .erpnext_manufacturing_prefix import (
    ERPNextManufacturingPrefixBuilder,
    _frappe_datetime,
)
from .erpnext_return_prefix import _payload
from .erpnext_shared_batch_evaluator import shared_batch_document_fingerprint
from .frappe import FrappeHTTPAdapter


def _money(value: Any) -> float:
    return float(Decimal(str(value)))


@dataclass(frozen=True)
class SharedBatchPrefix:
    scenario_id: str
    company: str
    shared_component: str
    primary_finished_item: str
    secondary_finished_item: str
    supplier_batch_id: str
    shared_purchase_receipt: str
    primary_purchase_receipt_item: str
    secondary_purchase_receipt_item: str
    shared_landed_cost_voucher: str
    primary_bom: str
    secondary_bom: str
    primary_work_order: str
    secondary_work_order: str
    primary_transfer: str
    secondary_transfer: str
    primary_material_quality_inspection: str
    secondary_material_quality_inspection: str
    accepted_primary_job_card: str
    rejected_primary_job_card: str
    secondary_job_card: str
    corrective_job_card: str
    rejected_quality_inspection: str
    accepted_primary_quality_inspection: str
    secondary_quality_inspection: str
    accepted_primary_manufacture: str
    secondary_manufacture: str
    customer_reservation: str
    stock_reservation_entry: str
    unrelated_receipt: str
    certificate_reference: str
    certificate_webhook: str
    quality_parameter: str
    accepted_quantity: float
    rework_quantity: float
    secondary_quantity: float
    expected_corrective_operation_cost: float
    protected_fingerprints: dict[str, str]
    evaluation_fixture: dict[str, Any]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


class ERPNextSharedBatchPrefixBuilder:
    """Create a shared-batch failure prefix through public ERPNext APIs.

    The supplier receipt, landed-cost update, both manufacturing branches and
    the customer stock reservation are native submitted documents.  No
    benchmark-side ledger row is fabricated.
    """

    STORES_WAREHOUSE = "Stores - AL"
    WIP_WAREHOUSE = "Manufacturing WIP - AL"
    FINISHED_WAREHOUSE = "Finished Goods - AL"
    SCRAP_WAREHOUSE = "Manufacturing Scrap - AL"
    SUPPLIER = "Aftermath Sensor Components Inc"
    CUSTOMER = "Aftermath Regional Cardiac Center"
    WORKSTATION_TYPE = "Clinical Device Final Assembly"
    WORKSTATION = "Clinical Assembly Cell 7"
    QUALITY_PARAMETER = "Clinical Device Functional Output"
    CERTIFICATE_WEBHOOK = "Aftermath Shared Batch Calibration Certificate"
    HOUR_RATE = 144

    def __init__(
        self,
        adapter: FrappeHTTPAdapter,
        *,
        scenario_id: str,
        fixture: dict[str, Any],
    ) -> None:
        self.adapter = adapter
        self.scenario_id = scenario_id
        self.fixture = fixture

    def _exists(self, doctype: str, name: str) -> bool:
        return bool(
            self.adapter.list_resources(
                doctype,
                fields=["name"],
                filters={"name": name},
                limit=1,
            ).get("data", [])
        )

    @staticmethod
    def _trace(
        trace: list[dict[str, Any]], tool: str, document: dict[str, Any]
    ) -> None:
        trace.append(
            {
                "kind": "write",
                "status": "success",
                "tool": tool,
                "doctype": document.get("doctype"),
                "name": document.get("name"),
            }
        )

    def _ensure_warehouse(self, warehouse_name: str) -> str:
        full_name = f"{warehouse_name} - {self.fixture['company_abbr']}"
        if not self._exists("Warehouse", full_name):
            created = _payload(
                self.adapter.create_resource(
                    "Warehouse",
                    {
                        "warehouse_name": warehouse_name,
                        "company": self.fixture["company"],
                        "is_group": 0,
                    },
                )
            )
            return str(created["name"])
        return full_name

    def _ensure_item(
        self,
        item: dict[str, Any],
        *,
        valuation_field: str,
        batch_tracked: bool = False,
    ) -> None:
        code = str(item["item_code"])
        if self._exists("Item", code):
            return
        rate = _money(item[valuation_field])
        payload: dict[str, Any] = {
            "item_code": code,
            "item_name": str(item["item_name"]),
            "description": str(item["item_name"]),
            "item_group": "Products",
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "valuation_rate": rate,
            "standard_rate": rate,
        }
        if batch_tracked:
            payload.update({"has_batch_no": 1, "create_new_batch": 0})
        self.adapter.create_resource("Item", payload)

    def prepare_public_fixture(self) -> dict[str, str]:
        if self.fixture["company"] != "Aftermath Laboratories LLC":
            raise ValueError("shared-batch fixture must use the initialized company")
        if self.fixture["company_abbr"] != "AL":
            raise ValueError("shared-batch fixture company abbreviation must be AL")

        warehouses = {
            "wip": self._ensure_warehouse("Manufacturing WIP"),
            "finished": self._ensure_warehouse("Finished Goods"),
            "scrap": self._ensure_warehouse("Manufacturing Scrap"),
        }
        shared = self.fixture["shared_component"]
        primary = self.fixture["primary_work_order"]
        secondary = self.fixture["secondary_work_order"]
        unrelated = self.fixture["unrelated_item"]
        self._ensure_item(shared, valuation_field="valuation_rate", batch_tracked=True)
        self._ensure_item(primary, valuation_field="output_valuation_rate")
        self._ensure_item(secondary, valuation_field="output_valuation_rate")
        self._ensure_item(unrelated, valuation_field="valuation_rate")

        if not self._exists("Supplier", self.SUPPLIER):
            self.adapter.create_resource(
                "Supplier",
                {
                    "supplier_name": self.SUPPLIER,
                    "supplier_type": "Company",
                    "supplier_group": "All Supplier Groups",
                    "country": "United States",
                },
            )
        if not self._exists("Customer", self.CUSTOMER):
            self.adapter.create_resource(
                "Customer",
                {
                    "customer_name": self.CUSTOMER,
                    "customer_type": "Company",
                    "customer_group": "Commercial",
                    "territory": "All Territories",
                },
            )
        if not self._exists("Workstation Type", self.WORKSTATION_TYPE):
            self.adapter.create_resource(
                "Workstation Type",
                {
                    "workstation_type": self.WORKSTATION_TYPE,
                    "hour_rate_labour": self.HOUR_RATE,
                },
            )
        if not self._exists("Workstation", self.WORKSTATION):
            self.adapter.create_resource(
                "Workstation",
                {
                    "workstation_name": self.WORKSTATION,
                    "workstation_type": self.WORKSTATION_TYPE,
                    "production_capacity": 1,
                    "hour_rate_labour": self.HOUR_RATE,
                    "status": "Production",
                },
            )
        operations = self.fixture["operations"]
        operation_specs = (
            (operations["assembly"], primary["accepted_quantity"], False),
            (operations["secondary_assembly"], secondary["accepted_quantity"], False),
            (operations["corrective"], None, True),
        )
        for name, batch_size, corrective in operation_specs:
            if self._exists("Operation", str(name)):
                continue
            document: dict[str, Any] = {
                "name": name,
                "workstation": self.WORKSTATION,
            }
            if batch_size is not None:
                document.update(
                    {
                        "create_job_card_based_on_batch_size": 1,
                        "batch_size": batch_size,
                    }
                )
            if corrective:
                document["is_corrective_operation"] = 1
            self.adapter.create_resource("Operation", document)
        if not self._exists("Quality Inspection Parameter", self.QUALITY_PARAMETER):
            self.adapter.create_resource(
                "Quality Inspection Parameter",
                {
                    "parameter": self.QUALITY_PARAMETER,
                    "description": "Functional output must equal one after calibration",
                },
            )
        self.adapter.update_resource(
            "Stock Settings",
            "Stock Settings",
            {
                "use_serial_batch_fields": 1,
                "enable_stock_reservation": 1,
                "auto_reserve_serial_and_batch": 1,
                "action_if_quality_inspection_is_rejected": "Stop",
            },
        )
        self.adapter.update_resource(
            "Manufacturing Settings",
            "Manufacturing Settings",
            {
                "default_wip_warehouse": warehouses["wip"],
                "default_fg_warehouse": warehouses["finished"],
                "default_scrap_warehouse": warehouses["scrap"],
                "add_corrective_operation_cost_in_finished_good_valuation": 1,
            },
        )
        key = str(self.fixture["external_certificate"]["idempotency_key"])
        if not self._exists("Webhook", self.CERTIFICATE_WEBHOOK):
            self.adapter.create_resource(
                "Webhook",
                {
                    "name": self.CERTIFICATE_WEBHOOK,
                    "webhook_doctype": "Job Card",
                    "webhook_docevent": "on_submit",
                    "enabled": 1,
                    "condition": "doc.is_corrective_job_card == 1",
                    "request_url": "http://remittance:8080/webhooks/events",
                    "request_method": "POST",
                    "request_structure": "JSON",
                    "background_jobs_queue": "short",
                    "webhook_json": (
                        '{"idempotency_key":"' + key + '","name":"{{ doc.name }}",'
                        '"quantity":{{ doc.total_completed_qty }},'
                        '"event":"calibration_certificate"}'
                    ),
                    "webhook_headers": [
                        {"key": "Content-Type", "value": "application/json"}
                    ],
                },
            )
        return warehouses

    def _create_bom(
        self,
        *,
        finished: dict[str, Any],
        operation: str,
        operation_batch_size: float,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        shared = self.fixture["shared_component"]
        bom = _payload(
            self.adapter.create_resource(
                "BOM",
                {
                    "item": finished["item_code"],
                    "company": self.fixture["company"],
                    "currency": "USD",
                    "quantity": 1,
                    "is_default": 1,
                    "is_active": 1,
                    "with_operations": 1,
                    "inspection_required": 1,
                    "items": [
                        {
                            "item_code": shared["item_code"],
                            "qty": finished["component_quantity_per_unit"],
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "rate": shared["valuation_rate"],
                            "source_warehouse": self.STORES_WAREHOUSE,
                        }
                    ],
                    "operations": [
                        {
                            "operation": operation,
                            "workstation": self.WORKSTATION,
                            "time_in_mins": 60,
                            "hour_rate": self.HOUR_RATE,
                            "batch_size": operation_batch_size,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create BOM", bom)
        bom = _payload(self.adapter.submit_document("BOM", str(bom["name"])))
        self._trace(trace, "submit BOM", bom)
        return bom

    def _create_work_order(
        self,
        *,
        bom: dict[str, Any],
        finished: dict[str, Any],
        quantity: float,
        now: datetime,
        warehouses: dict[str, str],
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.work_order.work_order.make_work_order",
                {
                    "bom_no": bom["name"],
                    "item": finished["item_code"],
                    "qty": quantity,
                    "company": self.fixture["company"],
                    "use_multi_level_bom": 0,
                },
            )
        )
        for field in ("name", "__islocal", "__unsaved"):
            template.pop(field, None)
        template.update(
            {
                "production_item": finished["item_code"],
                "bom_no": bom["name"],
                "qty": quantity,
                "company": self.fixture["company"],
                "stock_uom": "Nos",
                "source_warehouse": self.STORES_WAREHOUSE,
                "wip_warehouse": warehouses["wip"],
                "fg_warehouse": warehouses["finished"],
                "scrap_warehouse": warehouses["scrap"],
                "transfer_material_against": "Work Order",
                "planned_start_date": _frappe_datetime(now),
            }
        )
        work_order = _payload(self.adapter.create_resource("Work Order", template))
        self._trace(trace, "create Work Order", work_order)
        work_order = _payload(
            self.adapter.submit_document("Work Order", str(work_order["name"]))
        )
        self._trace(trace, "submit Work Order", work_order)
        return work_order

    def _make_stock_entry(
        self,
        *,
        work_order: str,
        purpose: str,
        quantity: float,
        batch_id: str,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
                {"work_order_id": work_order, "purpose": purpose, "qty": quantity},
            )
        )
        shared_code = self.fixture["shared_component"]["item_code"]
        for row in template.get("items", []):
            if row.get("item_code") == shared_code:
                row["use_serial_batch_fields"] = 1
                row["batch_no"] = batch_id
                row.pop("serial_and_batch_bundle", None)
        entry = _payload(self.adapter.create_resource("Stock Entry", template))
        self._trace(trace, f"create {purpose} Stock Entry", entry)
        return entry

    def _job_cards(self, work_order: str) -> list[dict[str, Any]]:
        summaries = self.adapter.list_resources(
            "Job Card",
            fields=["name", "for_quantity"],
            filters={"work_order": work_order},
            limit=20,
        ).get("data", [])
        return [
            _payload(self.adapter.get_resource("Job Card", str(row["name"])))
            for row in summaries
        ]

    def build(self) -> SharedBatchPrefix:
        warehouses = self.prepare_public_fixture()
        now = datetime.now(UTC).replace(microsecond=0)
        trace: list[dict[str, Any]] = []
        shared = self.fixture["shared_component"]
        primary = self.fixture["primary_work_order"]
        secondary = self.fixture["secondary_work_order"]
        unrelated = self.fixture["unrelated_item"]
        batch_id = str(shared["supplier_batch_id"])

        if not self._exists("Batch", batch_id):
            batch = _payload(
                self.adapter.create_resource(
                    "Batch",
                    {"batch_id": batch_id, "item": shared["item_code"]},
                )
            )
            self._trace(trace, "create supplier Batch", batch)

        receipt = _payload(
            self.adapter.create_resource(
                "Purchase Receipt",
                {
                    "company": self.fixture["company"],
                    "supplier": self.SUPPLIER,
                    "posting_date": now.date().isoformat(),
                    "currency": "USD",
                    "items": [
                        {
                            "item_code": shared["item_code"],
                            "received_qty": primary["ordered_quantity"],
                            "qty": primary["ordered_quantity"],
                            "rate": shared["valuation_rate"],
                            "warehouse": self.STORES_WAREHOUSE,
                            "use_serial_batch_fields": 1,
                            "batch_no": batch_id,
                        },
                        {
                            "item_code": shared["item_code"],
                            "received_qty": secondary["ordered_quantity"],
                            "qty": secondary["ordered_quantity"],
                            "rate": shared["valuation_rate"],
                            "warehouse": self.STORES_WAREHOUSE,
                            "use_serial_batch_fields": 1,
                            "batch_no": batch_id,
                        },
                    ],
                },
            )
        )
        self._trace(trace, "create shared-batch Purchase Receipt", receipt)
        receipt = _payload(
            self.adapter.submit_document("Purchase Receipt", str(receipt["name"]))
        )
        self._trace(trace, "submit shared-batch Purchase Receipt", receipt)
        receipt_rows = receipt.get("items", [])
        if len(receipt_rows) != 2:
            raise RuntimeError("shared Purchase Receipt must retain two native rows")
        rows_by_quantity = {
            float(row["qty"]): row
            for row in receipt_rows
            if row.get("item_code") == shared["item_code"]
        }
        primary_receipt_item = rows_by_quantity.get(float(primary["ordered_quantity"]))
        secondary_receipt_item = rows_by_quantity.get(
            float(secondary["ordered_quantity"])
        )
        if primary_receipt_item is None or secondary_receipt_item is None:
            raise RuntimeError("shared Purchase Receipt lost its 12/8 branch identity")

        expense_account = (
            f"Expenses Included In Valuation - {self.fixture['company_abbr']}"
        )
        landed_cost = _payload(
            self.adapter.create_resource(
                "Landed Cost Voucher",
                {
                    "company": self.fixture["company"],
                    "posting_date": now.date().isoformat(),
                    "distribute_charges_based_on": "Amount",
                    "purchase_receipts": [
                        {
                            "receipt_document_type": "Purchase Receipt",
                            "receipt_document": receipt["name"],
                            "supplier": receipt["supplier"],
                            "posting_date": receipt["posting_date"],
                            "grand_total": receipt["base_grand_total"],
                        }
                    ],
                    "taxes": [
                        {
                            "description": self.fixture["shared_landed_cost"][
                                "voucher_title"
                            ],
                            "expense_account": expense_account,
                            "amount": self.fixture["shared_landed_cost"]["amount"],
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create Landed Cost Voucher", landed_cost)
        landed_cost = _payload(
            self.adapter.submit_document(
                "Landed Cost Voucher", str(landed_cost["name"])
            )
        )
        self._trace(trace, "submit Landed Cost Voucher", landed_cost)

        unrelated_receipt = _payload(
            self.adapter.create_resource(
                "Stock Entry",
                {
                    "stock_entry_type": "Material Receipt",
                    "company": self.fixture["company"],
                    "posting_date": now.date().isoformat(),
                    "items": [
                        {
                            "item_code": unrelated["item_code"],
                            "qty": unrelated["quantity"],
                            "basic_rate": unrelated["valuation_rate"],
                            "t_warehouse": self.STORES_WAREHOUSE,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create unrelated inventory receipt", unrelated_receipt)
        unrelated_receipt = _payload(
            self.adapter.submit_document("Stock Entry", str(unrelated_receipt["name"]))
        )
        self._trace(trace, "submit unrelated inventory receipt", unrelated_receipt)

        primary_bom = self._create_bom(
            finished=primary,
            operation=self.fixture["operations"]["assembly"],
            operation_batch_size=float(primary["accepted_quantity"]),
            trace=trace,
        )
        secondary_bom = self._create_bom(
            finished=secondary,
            operation=self.fixture["operations"]["secondary_assembly"],
            operation_batch_size=float(secondary["accepted_quantity"]),
            trace=trace,
        )
        primary_wo = self._create_work_order(
            bom=primary_bom,
            finished=primary,
            quantity=float(primary["ordered_quantity"]),
            now=now,
            warehouses=warehouses,
            trace=trace,
        )
        secondary_wo = self._create_work_order(
            bom=secondary_bom,
            finished=secondary,
            quantity=float(secondary["ordered_quantity"]),
            now=now + timedelta(hours=1),
            warehouses=warehouses,
            trace=trace,
        )

        helper_fixture = {
            "quality_parameter": self.QUALITY_PARAMETER,
            "corrective_operation": self.fixture["operations"]["corrective"],
            "hour_rate": self.HOUR_RATE,
        }
        helper = ERPNextManufacturingPrefixBuilder(
            self.adapter, scenario_id=self.scenario_id, fixture=helper_fixture
        )

        primary_transfer = self._make_stock_entry(
            work_order=str(primary_wo["name"]),
            purpose="Material Transfer for Manufacture",
            quantity=float(primary["ordered_quantity"]),
            batch_id=batch_id,
            trace=trace,
        )
        primary_material_qi = helper._create_inspection(
            reference_type="Stock Entry",
            reference_name=str(primary_transfer["name"]),
            item_code=str(shared["item_code"]),
            quantity=float(primary["ordered_quantity"]),
            accepted=True,
            trace=trace,
        )
        primary_transfer = _payload(
            self.adapter.submit_document("Stock Entry", str(primary_transfer["name"]))
        )
        self._trace(trace, "submit primary material transfer", primary_transfer)
        secondary_transfer = self._make_stock_entry(
            work_order=str(secondary_wo["name"]),
            purpose="Material Transfer for Manufacture",
            quantity=float(secondary["ordered_quantity"]),
            batch_id=batch_id,
            trace=trace,
        )
        secondary_material_qi = helper._create_inspection(
            reference_type="Stock Entry",
            reference_name=str(secondary_transfer["name"]),
            item_code=str(shared["item_code"]),
            quantity=float(secondary["ordered_quantity"]),
            accepted=True,
            trace=trace,
        )
        secondary_transfer = _payload(
            self.adapter.submit_document("Stock Entry", str(secondary_transfer["name"]))
        )
        self._trace(trace, "submit secondary material transfer", secondary_transfer)

        primary_cards = self._job_cards(str(primary_wo["name"]))
        accepted_quantity = float(primary["accepted_quantity"])
        rework_quantity = float(primary["rework_quantity"])
        accepted_cards = [
            card
            for card in primary_cards
            if float(card["for_quantity"]) == accepted_quantity
        ]
        rejected_cards = [
            card
            for card in primary_cards
            if float(card["for_quantity"]) == rework_quantity
        ]
        if len(accepted_cards) != 1 or len(rejected_cards) != 1:
            raise RuntimeError(
                "primary Work Order did not create the 9/3 Job Card split"
            )
        accepted_job = helper._complete_job_card(
            accepted_cards[0], start=now + timedelta(hours=2), trace=trace
        )
        rejected_job = helper._complete_job_card(
            rejected_cards[0], start=now + timedelta(hours=4), trace=trace
        )
        secondary_cards = self._job_cards(str(secondary_wo["name"]))
        if len(secondary_cards) != 1:
            raise RuntimeError("secondary Work Order must create exactly one Job Card")
        secondary_job = helper._complete_job_card(
            secondary_cards[0], start=now + timedelta(hours=6), trace=trace
        )

        rejected_qi = helper._create_inspection(
            reference_type="Job Card",
            reference_name=str(rejected_job["name"]),
            item_code=str(primary["item_code"]),
            quantity=rework_quantity,
            accepted=False,
            trace=trace,
        )
        accepted_entry = self._make_stock_entry(
            work_order=str(primary_wo["name"]),
            purpose="Manufacture",
            quantity=accepted_quantity,
            batch_id=batch_id,
            trace=trace,
        )
        accepted_qi = helper._create_inspection(
            reference_type="Stock Entry",
            reference_name=str(accepted_entry["name"]),
            item_code=str(primary["item_code"]),
            quantity=accepted_quantity,
            accepted=True,
            trace=trace,
        )
        accepted_entry = _payload(
            self.adapter.submit_document("Stock Entry", str(accepted_entry["name"]))
        )
        self._trace(trace, "submit accepted primary manufacture", accepted_entry)

        secondary_entry = self._make_stock_entry(
            work_order=str(secondary_wo["name"]),
            purpose="Manufacture",
            quantity=float(secondary["accepted_quantity"]),
            batch_id=batch_id,
            trace=trace,
        )
        secondary_qi = helper._create_inspection(
            reference_type="Stock Entry",
            reference_name=str(secondary_entry["name"]),
            item_code=str(secondary["item_code"]),
            quantity=float(secondary["accepted_quantity"]),
            accepted=True,
            trace=trace,
        )
        secondary_entry = _payload(
            self.adapter.submit_document("Stock Entry", str(secondary_entry["name"]))
        )
        self._trace(trace, "submit secondary manufacture", secondary_entry)

        reservation = self.fixture["customer_reservation"]
        sales_order = _payload(
            self.adapter.create_resource(
                "Sales Order",
                {
                    "naming_series": "SO-CROSS-.###",
                    "company": self.fixture["company"],
                    "customer": self.CUSTOMER,
                    "transaction_date": now.date().isoformat(),
                    "delivery_date": (now.date() + timedelta(days=7)).isoformat(),
                    "currency": "USD",
                    "reserve_stock": 1,
                    "items": [
                        {
                            "item_code": secondary["item_code"],
                            "qty": reservation["quantity"],
                            "rate": secondary["output_valuation_rate"],
                            "warehouse": warehouses["finished"],
                            "delivery_date": (
                                now.date() + timedelta(days=7)
                            ).isoformat(),
                            "reserve_stock": 1,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create protected customer Sales Order", sales_order)
        sales_order = _payload(
            self.adapter.submit_document("Sales Order", str(sales_order["name"]))
        )
        self._trace(trace, "submit protected customer Sales Order", sales_order)
        if str(sales_order["name"]) != str(reservation["sales_order"]):
            raise RuntimeError(
                f"expected customer reservation {reservation['sales_order']}, "
                f"observed {sales_order['name']}"
            )
        reservations = self.adapter.list_resources(
            "Stock Reservation Entry",
            fields=["name", "reserved_qty", "status"],
            filters={"voucher_type": "Sales Order", "voucher_no": sales_order["name"]},
            limit=20,
        ).get("data", [])
        if len(reservations) != 1:
            raise RuntimeError("Sales Order must create exactly one stock reservation")

        corrective_template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.job_card.job_card.make_corrective_job_card",
                {
                    "source_name": rejected_job["name"],
                    "operation": self.fixture["operations"]["corrective"],
                    "for_operation": rejected_job.get("operation"),
                },
            )
        )
        corrective_template["hour_rate"] = self.HOUR_RATE
        corrective_template["time_logs"] = [
            {
                "from_time": _frappe_datetime(now + timedelta(hours=8)),
                "to_time": _frappe_datetime(now + timedelta(hours=9)),
                "time_in_mins": 60,
                "completed_qty": rework_quantity,
            }
        ]
        corrective = _payload(
            self.adapter.create_resource("Job Card", corrective_template)
        )
        self._trace(trace, "create corrective Job Card", corrective)

        protected_documents = {
            "accepted_primary_manufacture": _payload(
                self.adapter.get_resource("Stock Entry", str(accepted_entry["name"]))
            ),
            "secondary_manufacture": _payload(
                self.adapter.get_resource("Stock Entry", str(secondary_entry["name"]))
            ),
            "customer_reservation": _payload(
                self.adapter.get_resource("Sales Order", str(sales_order["name"]))
            ),
            "shared_landed_cost_voucher": _payload(
                self.adapter.get_resource(
                    "Landed Cost Voucher", str(landed_cost["name"])
                )
            ),
            "unrelated_receipt": _payload(
                self.adapter.get_resource("Stock Entry", str(unrelated_receipt["name"]))
            ),
        }
        return SharedBatchPrefix(
            scenario_id=self.scenario_id,
            company=str(self.fixture["company"]),
            shared_component=str(shared["item_code"]),
            primary_finished_item=str(primary["item_code"]),
            secondary_finished_item=str(secondary["item_code"]),
            supplier_batch_id=batch_id,
            shared_purchase_receipt=str(receipt["name"]),
            primary_purchase_receipt_item=str(primary_receipt_item["name"]),
            secondary_purchase_receipt_item=str(secondary_receipt_item["name"]),
            shared_landed_cost_voucher=str(landed_cost["name"]),
            primary_bom=str(primary_bom["name"]),
            secondary_bom=str(secondary_bom["name"]),
            primary_work_order=str(primary_wo["name"]),
            secondary_work_order=str(secondary_wo["name"]),
            primary_transfer=str(primary_transfer["name"]),
            secondary_transfer=str(secondary_transfer["name"]),
            primary_material_quality_inspection=str(primary_material_qi["name"]),
            secondary_material_quality_inspection=str(secondary_material_qi["name"]),
            accepted_primary_job_card=str(accepted_job["name"]),
            rejected_primary_job_card=str(rejected_job["name"]),
            secondary_job_card=str(secondary_job["name"]),
            corrective_job_card=str(corrective["name"]),
            rejected_quality_inspection=str(rejected_qi["name"]),
            accepted_primary_quality_inspection=str(accepted_qi["name"]),
            secondary_quality_inspection=str(secondary_qi["name"]),
            accepted_primary_manufacture=str(accepted_entry["name"]),
            secondary_manufacture=str(secondary_entry["name"]),
            customer_reservation=str(sales_order["name"]),
            stock_reservation_entry=str(reservations[0]["name"]),
            unrelated_receipt=str(unrelated_receipt["name"]),
            certificate_reference=str(
                self.fixture["external_certificate"]["idempotency_key"]
            ),
            certificate_webhook=self.CERTIFICATE_WEBHOOK,
            quality_parameter=self.QUALITY_PARAMETER,
            accepted_quantity=accepted_quantity,
            rework_quantity=rework_quantity,
            secondary_quantity=float(secondary["accepted_quantity"]),
            expected_corrective_operation_cost=float(self.HOUR_RATE),
            protected_fingerprints={
                key: shared_batch_document_fingerprint(document)
                for key, document in protected_documents.items()
            },
            evaluation_fixture=copy.deepcopy(self.fixture),
            trace=tuple(trace),
        )


__all__ = ["ERPNextSharedBatchPrefixBuilder", "SharedBatchPrefix"]
