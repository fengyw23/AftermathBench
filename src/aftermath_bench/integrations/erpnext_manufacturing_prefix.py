from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from .erpnext_manufacturing_evaluator import manufacturing_document_fingerprint
from .erpnext_return_prefix import _payload
from .frappe import FrappeHTTPAdapter


def _money(value: Any) -> float:
    return float(Decimal(str(value)))


def _frappe_datetime(value: datetime) -> str:
    return value.astimezone(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class ManufacturingPrefix:
    scenario_id: str
    company: str
    bom: str
    work_order: str
    finished_item: str
    raw_items: tuple[str, ...]
    accepted_quantity: float
    rework_quantity: float
    accepted_job_card: str
    rejected_job_card: str
    corrective_job_card: str
    accepted_quality_inspection: str
    rejected_quality_inspection: str
    material_quality_inspections: tuple[str, ...]
    accepted_manufacture_stock_entry: str
    material_transfer_stock_entry: str
    unrelated_stock_entry: str
    corrective_operation: str
    quality_parameter: str
    quality_release_webhook: str
    expected_corrective_operation_cost: float
    protected_fingerprints: dict[str, str]
    trace: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


class ERPNextManufacturingPrefixBuilder:
    STORES_WAREHOUSE = "Stores - AL"
    WIP_WAREHOUSE = "Manufacturing WIP - AL"
    FINISHED_WAREHOUSE = "Finished Goods - AL"
    SCRAP_WAREHOUSE = "Manufacturing Scrap - AL"
    QUALITY_RELEASE_WEBHOOK = "Aftermath Corrective Job Quality Release"

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
        trace: list[dict[str, Any]],
        tool: str,
        document: dict[str, Any],
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

    def _ensure_item(self, item: dict[str, Any]) -> None:
        code = str(item["item_code"])
        if self._exists("Item", code):
            return
        self.adapter.create_resource(
            "Item",
            {
                "item_code": code,
                "item_name": item["item_name"],
                "description": item.get("description", item["item_name"]),
                "item_group": "Products",
                "stock_uom": "Nos",
                "is_stock_item": 1,
                "valuation_rate": _money(item["valuation_rate"]),
                "standard_rate": _money(item["valuation_rate"]),
            },
        )

    def prepare_public_fixture(self) -> dict[str, str]:
        wip = self._ensure_warehouse("Manufacturing WIP")
        finished = self._ensure_warehouse("Finished Goods")
        scrap = self._ensure_warehouse("Manufacturing Scrap")
        for item in (
            *self.fixture["raw_items"],
            self.fixture["finished_item"],
            self.fixture["unrelated_item"],
        ):
            self._ensure_item(item)

        workstation_type = str(self.fixture["workstation_type"])
        if not self._exists("Workstation Type", workstation_type):
            self.adapter.create_resource(
                "Workstation Type",
                {
                    "workstation_type": workstation_type,
                    "hour_rate_labour": self.fixture["hour_rate"],
                },
            )
        workstation = str(self.fixture["workstation"])
        if not self._exists("Workstation", workstation):
            self.adapter.create_resource(
                "Workstation",
                {
                    "workstation_name": workstation,
                    "workstation_type": workstation_type,
                    "production_capacity": 1,
                    "hour_rate_labour": self.fixture["hour_rate"],
                    "status": "Production",
                },
            )
        assembly = str(self.fixture["assembly_operation"])
        if not self._exists("Operation", assembly):
            self.adapter.create_resource(
                "Operation",
                {
                    "name": assembly,
                    "workstation": workstation,
                    "create_job_card_based_on_batch_size": 1,
                    "batch_size": self.fixture["accepted_quantity"],
                },
            )
        corrective = str(self.fixture["corrective_operation"])
        if not self._exists("Operation", corrective):
            self.adapter.create_resource(
                "Operation",
                {
                    "name": corrective,
                    "workstation": workstation,
                    "is_corrective_operation": 1,
                },
            )
        parameter = str(self.fixture["quality_parameter"])
        if not self._exists("Quality Inspection Parameter", parameter):
            self.adapter.create_resource(
                "Quality Inspection Parameter",
                {
                    "parameter": parameter,
                    "description": "Functional output must equal one after calibration",
                },
            )
        self.adapter.update_resource(
            "Stock Settings",
            "Stock Settings",
            {"action_if_quality_inspection_is_rejected": "Stop"},
        )
        self.adapter.update_resource(
            "Manufacturing Settings",
            "Manufacturing Settings",
            {
                "default_wip_warehouse": wip,
                "default_fg_warehouse": finished,
                "default_scrap_warehouse": scrap,
                "add_corrective_operation_cost_in_finished_good_valuation": 1,
            },
        )
        if not self._exists("Webhook", self.QUALITY_RELEASE_WEBHOOK):
            self.adapter.create_resource(
                "Webhook",
                {
                    "name": self.QUALITY_RELEASE_WEBHOOK,
                    "webhook_doctype": "Job Card",
                    "webhook_docevent": "on_submit",
                    "enabled": 1,
                    "condition": "doc.is_corrective_job_card == 1",
                    "request_url": "http://remittance:8080/webhooks/events",
                    "request_method": "POST",
                    "request_structure": "JSON",
                    "background_jobs_queue": "short",
                    "webhook_json": (
                        '{"name":"{{ doc.name }}",'
                        '"work_order":"{{ doc.work_order }}",'
                        '"event":"corrective_job_quality_release"}'
                    ),
                    "webhook_headers": [
                        {"key": "Content-Type", "value": "application/json"}
                    ],
                },
            )
        return {"wip": wip, "finished": finished, "scrap": scrap}

    def _create_inspection(
        self,
        *,
        reference_type: str,
        reference_name: str,
        item_code: str,
        quantity: float,
        accepted: bool,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        inspection = _payload(
            self.adapter.create_resource(
                "Quality Inspection",
                {
                    "inspection_type": (
                        "Incoming" if reference_type == "Stock Entry" else "In Process"
                    ),
                    "reference_type": reference_type,
                    "reference_name": reference_name,
                    "item_code": item_code,
                    "sample_size": quantity,
                    "inspected_by": "Administrator",
                    "readings": [
                        {
                            "specification": self.fixture["quality_parameter"],
                            "min_value": 1,
                            "max_value": 1,
                            "reading_1": "1" if accepted else "0",
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create Quality Inspection", inspection)
        inspection = _payload(
            self.adapter.submit_document("Quality Inspection", inspection["name"])
        )
        self._trace(trace, "submit Quality Inspection", inspection)
        expected = "Accepted" if accepted else "Rejected"
        if inspection.get("status") != expected:
            raise RuntimeError(
                f"inspection {inspection['name']} status={inspection.get('status')} expected={expected}"
            )
        return inspection

    def _complete_job_card(
        self,
        job_card: dict[str, Any],
        *,
        start: datetime,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        quantity = float(job_card["for_quantity"])
        updated = _payload(
            self.adapter.update_resource(
                "Job Card",
                str(job_card["name"]),
                {
                    "time_logs": [
                        {
                            "from_time": _frappe_datetime(start),
                            "to_time": _frappe_datetime(start + timedelta(minutes=60)),
                            "time_in_mins": 60,
                            "completed_qty": quantity,
                        }
                    ]
                },
            )
        )
        self._trace(trace, "record Job Card time", updated)
        submitted = _payload(
            self.adapter.submit_document("Job Card", str(job_card["name"]))
        )
        self._trace(trace, "submit Job Card", submitted)
        return submitted

    def _make_work_order_stock_entry(
        self,
        *,
        work_order: str,
        purpose: str,
        quantity: float,
        trace: list[dict[str, Any]],
    ) -> dict[str, Any]:
        template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
                {
                    "work_order_id": work_order,
                    "purpose": purpose,
                    "qty": quantity,
                },
            )
        )
        document = _payload(self.adapter.create_resource("Stock Entry", template))
        self._trace(trace, f"create {purpose} Stock Entry", document)
        return document

    def build(self) -> ManufacturingPrefix:
        warehouses = self.prepare_public_fixture()
        now = datetime.now(UTC).replace(microsecond=0)
        trace: list[dict[str, Any]] = []
        company = str(self.fixture["company"])
        finished = self.fixture["finished_item"]
        raw_items = tuple(str(row["item_code"]) for row in self.fixture["raw_items"])
        accepted_quantity = float(self.fixture["accepted_quantity"])
        rework_quantity = float(self.fixture["rework_quantity"])
        total_quantity = accepted_quantity + rework_quantity

        unrelated = self.fixture["unrelated_item"]
        seed = _payload(
            self.adapter.create_resource(
                "Stock Entry",
                {
                    "stock_entry_type": "Material Receipt",
                    "company": company,
                    "posting_date": now.date().isoformat(),
                    "items": [
                        *(
                            {
                                "item_code": item["item_code"],
                                "qty": total_quantity
                                * float(item.get("quantity_per_unit", 1)),
                                "basic_rate": item["valuation_rate"],
                                "t_warehouse": self.STORES_WAREHOUSE,
                            }
                            for item in self.fixture["raw_items"]
                        ),
                        {
                            "item_code": unrelated["item_code"],
                            "qty": unrelated["quantity"],
                            "basic_rate": unrelated["valuation_rate"],
                            "t_warehouse": self.STORES_WAREHOUSE,
                        },
                    ],
                },
            )
        )
        self._trace(trace, "create material and unrelated stock receipt", seed)
        seed = _payload(self.adapter.submit_document("Stock Entry", seed["name"]))
        self._trace(trace, "submit material and unrelated stock receipt", seed)

        bom = _payload(
            self.adapter.create_resource(
                "BOM",
                {
                    "item": finished["item_code"],
                    "company": company,
                    "currency": "USD",
                    "quantity": 1,
                    "is_default": 1,
                    "is_active": 1,
                    "with_operations": 1,
                    "inspection_required": 1,
                    "items": [
                        {
                            "item_code": item["item_code"],
                            "qty": item.get("quantity_per_unit", 1),
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "rate": item["valuation_rate"],
                            "source_warehouse": self.STORES_WAREHOUSE,
                        }
                        for item in self.fixture["raw_items"]
                    ],
                    "operations": [
                        {
                            "operation": self.fixture["assembly_operation"],
                            "workstation": self.fixture["workstation"],
                            "time_in_mins": 60,
                            "hour_rate": self.fixture["hour_rate"],
                            "batch_size": accepted_quantity,
                        }
                    ],
                },
            )
        )
        self._trace(trace, "create BOM", bom)
        bom = _payload(self.adapter.submit_document("BOM", bom["name"]))
        self._trace(trace, "submit BOM", bom)

        # The ERPNext form calls ``make_work_order`` when a BOM is selected.
        # A bare REST insert does not perform that client-side transition, so
        # it can create a Work Order with required items but no operations and
        # therefore no Job Cards.  Obtain the draft from ERPNext's own factory
        # instead of reproducing BOM expansion in benchmark code.
        work_order_template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.work_order.work_order.make_work_order",
                {
                    "bom_no": bom["name"],
                    "item": finished["item_code"],
                    "qty": total_quantity,
                    "company": company,
                    "use_multi_level_bom": 0,
                },
            )
        )
        for transient_field in ("name", "__islocal", "__unsaved"):
            work_order_template.pop(transient_field, None)
        work_order_template.update(
            {
                "production_item": finished["item_code"],
                "bom_no": bom["name"],
                "qty": total_quantity,
                "company": company,
                "stock_uom": "Nos",
                "source_warehouse": self.STORES_WAREHOUSE,
                "wip_warehouse": warehouses["wip"],
                "fg_warehouse": warehouses["finished"],
                "scrap_warehouse": warehouses["scrap"],
                "transfer_material_against": "Work Order",
                "planned_start_date": _frappe_datetime(now),
            }
        )
        work_order = _payload(
            self.adapter.create_resource("Work Order", work_order_template)
        )
        self._trace(trace, "create Work Order", work_order)
        work_order = _payload(
            self.adapter.submit_document("Work Order", work_order["name"])
        )
        self._trace(trace, "submit Work Order", work_order)

        transfer = self._make_work_order_stock_entry(
            work_order=str(work_order["name"]),
            purpose="Material Transfer for Manufacture",
            quantity=total_quantity,
            trace=trace,
        )
        material_inspections = []
        for item in transfer.get("items", []):
            if not item.get("t_warehouse"):
                continue
            inspection = self._create_inspection(
                reference_type="Stock Entry",
                reference_name=str(transfer["name"]),
                item_code=str(item["item_code"]),
                quantity=float(item["qty"]),
                accepted=True,
                trace=trace,
            )
            material_inspections.append(str(inspection["name"]))
        if len(material_inspections) != len(self.fixture["raw_items"]):
            raise RuntimeError(
                "each transferred raw-material row requires one accepted inspection"
            )
        transfer = _payload(
            self.adapter.submit_document("Stock Entry", transfer["name"])
        )
        self._trace(trace, "submit Material Transfer for Manufacture", transfer)

        summaries = self.adapter.list_resources(
            "Job Card",
            fields=["name", "for_quantity"],
            filters={"work_order": work_order["name"]},
            limit=20,
        ).get("data", [])
        job_cards = [
            _payload(self.adapter.get_resource("Job Card", str(row["name"])))
            for row in summaries
        ]
        by_quantity: dict[float, list[dict[str, Any]]] = {}
        for card in job_cards:
            by_quantity.setdefault(float(card["for_quantity"]), []).append(card)
        if (
            len(by_quantity.get(accepted_quantity, [])) != 1
            or len(by_quantity.get(rework_quantity, [])) != 1
        ):
            raise RuntimeError(
                "expected one accepted and one rejected Job Card; "
                f"observed={[card.get('for_quantity') for card in job_cards]}"
            )
        accepted_job = self._complete_job_card(
            by_quantity[accepted_quantity][0], start=now, trace=trace
        )
        rejected_job = self._complete_job_card(
            by_quantity[rework_quantity][0],
            start=now + timedelta(hours=2),
            trace=trace,
        )
        rejected_inspection = self._create_inspection(
            reference_type="Job Card",
            reference_name=str(rejected_job["name"]),
            item_code=str(finished["item_code"]),
            quantity=rework_quantity,
            accepted=False,
            trace=trace,
        )

        accepted_entry = self._make_work_order_stock_entry(
            work_order=str(work_order["name"]),
            purpose="Manufacture",
            quantity=accepted_quantity,
            trace=trace,
        )
        accepted_inspection = self._create_inspection(
            reference_type="Stock Entry",
            reference_name=str(accepted_entry["name"]),
            item_code=str(finished["item_code"]),
            quantity=accepted_quantity,
            accepted=True,
            trace=trace,
        )
        accepted_entry = _payload(
            self.adapter.submit_document("Stock Entry", accepted_entry["name"])
        )
        self._trace(trace, "submit accepted Manufacture Stock Entry", accepted_entry)

        corrective_template = _payload(
            self.adapter.call_method(
                "erpnext.manufacturing.doctype.job_card.job_card.make_corrective_job_card",
                {
                    "source_name": rejected_job["name"],
                    "operation": self.fixture["corrective_operation"],
                    "for_operation": rejected_job.get("operation"),
                },
            )
        )
        corrective_template["hour_rate"] = self.fixture["hour_rate"]
        corrective_template["time_logs"] = [
            {
                "from_time": _frappe_datetime(now + timedelta(hours=4)),
                "to_time": _frappe_datetime(now + timedelta(hours=5)),
                "time_in_mins": 60,
                "completed_qty": rework_quantity,
            }
        ]
        corrective = _payload(
            self.adapter.create_resource("Job Card", corrective_template)
        )
        self._trace(trace, "create corrective Job Card", corrective)

        return ManufacturingPrefix(
            scenario_id=self.scenario_id,
            company=company,
            bom=str(bom["name"]),
            work_order=str(work_order["name"]),
            finished_item=str(finished["item_code"]),
            raw_items=raw_items,
            accepted_quantity=accepted_quantity,
            rework_quantity=rework_quantity,
            accepted_job_card=str(accepted_job["name"]),
            rejected_job_card=str(rejected_job["name"]),
            corrective_job_card=str(corrective["name"]),
            accepted_quality_inspection=str(accepted_inspection["name"]),
            rejected_quality_inspection=str(rejected_inspection["name"]),
            material_quality_inspections=tuple(material_inspections),
            accepted_manufacture_stock_entry=str(accepted_entry["name"]),
            material_transfer_stock_entry=str(transfer["name"]),
            unrelated_stock_entry=str(seed["name"]),
            corrective_operation=str(self.fixture["corrective_operation"]),
            quality_parameter=str(self.fixture["quality_parameter"]),
            quality_release_webhook=self.QUALITY_RELEASE_WEBHOOK,
            expected_corrective_operation_cost=_money(self.fixture["hour_rate"]),
            protected_fingerprints={
                "accepted_manufacture_stock_entry": manufacturing_document_fingerprint(
                    accepted_entry
                ),
                "accepted_job_card": manufacturing_document_fingerprint(accepted_job),
                "bom": manufacturing_document_fingerprint(bom),
                "unrelated_stock_entry": manufacturing_document_fingerprint(seed),
            },
            trace=tuple(trace),
        )


__all__ = [
    "ERPNextManufacturingPrefixBuilder",
    "ManufacturingPrefix",
]
