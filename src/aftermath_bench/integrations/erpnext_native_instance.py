from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{2,127}$")
SUPPORTED_FAMILIES = frozenset(
    {
        "erpnext-manufacturing-rework",
        "erpnext-multiwarehouse-transfer",
        "erpnext-shared-batch-recovery",
    }
)


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class ERPNextNativeInstanceSpec:
    schema_version: str
    scenario_id: str
    family: str
    title: str
    user_instruction: str
    fixture: dict[str, Any]

    @classmethod
    def from_path(cls, path: str | Path) -> "ERPNextNativeInstanceSpec":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("ERPNext instance specification must be an object")
        expected = {
            "schema_version",
            "scenario_id",
            "family",
            "title",
            "user_instruction",
            "fixture",
        }
        if set(payload) != expected:
            raise ValueError(
                "ERPNext instance specification fields do not match the schema"
            )
        instance = cls(
            schema_version=str(payload["schema_version"]),
            scenario_id=str(payload["scenario_id"]),
            family=str(payload["family"]),
            title=str(payload["title"]),
            user_instruction=str(payload["user_instruction"]),
            fixture=copy.deepcopy(payload["fixture"]),
        )
        instance.validate()
        return instance

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise ValueError("ERPNext instance schema_version must be 1.0")
        if _IDENTIFIER.fullmatch(self.scenario_id) is None:
            raise ValueError("ERPNext instance scenario_id is invalid")
        if self.family not in SUPPORTED_FAMILIES:
            raise ValueError("ERPNext instance family is unsupported")
        if not self.title.strip() or not self.user_instruction.strip():
            raise ValueError("ERPNext instance title and instruction are required")
        if not isinstance(self.fixture, dict) or len(self.fixture) < 6:
            raise ValueError("ERPNext instance fixture is not a substantive object")
        if self.family == "erpnext-shared-batch-recovery":
            self._validate_shared_batch_fixture()

    def _validate_shared_batch_fixture(self) -> None:
        required = {
            "company",
            "company_abbr",
            "shared_component",
            "primary_work_order",
            "secondary_work_order",
            "shared_landed_cost",
            "customer_reservation",
            "external_certificate",
            "unrelated_item",
            "operations",
        }
        if set(self.fixture) != required:
            raise ValueError("shared-batch fixture fields do not match the schema")
        shared = self.fixture["shared_component"]
        primary = self.fixture["primary_work_order"]
        secondary = self.fixture["secondary_work_order"]
        if not all(isinstance(item, dict) for item in (shared, primary, secondary)):
            raise ValueError("shared-batch work-order records must be objects")
        numeric_fields = (
            (shared, "received_quantity"),
            (shared, "valuation_rate"),
            (primary, "ordered_quantity"),
            (primary, "accepted_quantity"),
            (primary, "rework_quantity"),
            (primary, "component_quantity_per_unit"),
            (secondary, "ordered_quantity"),
            (secondary, "accepted_quantity"),
            (secondary, "component_quantity_per_unit"),
        )
        if any(
            isinstance(record.get(field), bool)
            or not isinstance(record.get(field), (int, float))
            or record[field] <= 0
            for record, field in numeric_fields
        ):
            raise ValueError("shared-batch quantities and rates must be positive")
        if (
            primary["accepted_quantity"] + primary["rework_quantity"]
            != primary["ordered_quantity"]
        ):
            raise ValueError("primary accepted and rework quantities must close the order")
        if secondary["accepted_quantity"] != secondary["ordered_quantity"]:
            raise ValueError("secondary work order must be accepted at the boundary")
        required_component_quantity = (
            primary["ordered_quantity"] * primary["component_quantity_per_unit"]
            + secondary["ordered_quantity"]
            * secondary["component_quantity_per_unit"]
        )
        if shared["received_quantity"] < required_component_quantity:
            raise ValueError("shared supplier batch cannot cover both work orders")
        landed_cost = self.fixture["shared_landed_cost"]
        reservation = self.fixture["customer_reservation"]
        certificate = self.fixture["external_certificate"]
        if not all(
            isinstance(item, dict)
            for item in (landed_cost, reservation, certificate)
        ):
            raise ValueError("shared-batch obligations must be objects")
        allocations = (
            landed_cost.get("primary_allocation"),
            landed_cost.get("secondary_allocation"),
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
            for value in (*allocations, landed_cost.get("amount"))
        ):
            raise ValueError("shared landed-cost amounts must be positive")
        if sum(allocations) != landed_cost["amount"]:
            raise ValueError("shared landed-cost allocations must sum to the voucher")
        if (
            reservation.get("item_code") != secondary.get("item_code")
            or reservation.get("quantity") != secondary.get("accepted_quantity")
        ):
            raise ValueError("customer reservation must protect all secondary output")
        if certificate.get("required_quantity") != primary.get("rework_quantity"):
            raise ValueError("certificate quantity must match the corrective branch")
        if not str(certificate.get("idempotency_key", "")).strip():
            raise ValueError("external certificate needs an idempotency key")
        item_codes = {
            str(shared.get("item_code", "")),
            str(primary.get("item_code", "")),
            str(secondary.get("item_code", "")),
            str(self.fixture["unrelated_item"].get("item_code", "")),
        }
        if "" in item_codes or len(item_codes) != 4:
            raise ValueError("shared-batch native item codes must be nonempty and unique")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "family": self.family,
            "title": self.title,
            "user_instruction": self.user_instruction,
            "fixture": copy.deepcopy(self.fixture),
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict())).hexdigest()


def render_erpnext_native_blueprint(
    instance: ERPNextNativeInstanceSpec,
    *,
    template: dict[str, Any],
    instance_id: str,
    benchmark_split: str,
) -> dict[str, Any]:
    instance.validate()
    if benchmark_split not in {"development", "public_dev", "hidden_test"}:
        raise ValueError("unsupported benchmark split")
    if template.get("family") != instance.family:
        raise ValueError("ERPNext instance family does not match its template")
    if _IDENTIFIER.fullmatch(instance_id) is None:
        raise ValueError("ERPNext benchmark instance_id is invalid")
    payload = copy.deepcopy(template)
    payload.update(
        {
            "scenario_id": instance.scenario_id,
            "instance_id": instance_id,
            "benchmark_split": benchmark_split,
            "benchmark_tier": "unvalidated",
            "hidden_test_eligible": benchmark_split == "hidden_test",
            "implementation_status": "native replay pending",
            "title": instance.title,
            "user_instruction": instance.user_instruction,
            "fixture": copy.deepcopy(instance.fixture),
            "instance_spec_sha256": instance.sha256,
        }
    )
    if instance.family == "erpnext-manufacturing-rework":
        rework_quantity = instance.fixture.get("rework_quantity")
        if not isinstance(rework_quantity, (int, float)) or rework_quantity <= 0:
            raise ValueError(
                "manufacturing instance rework_quantity must be positive"
            )
        rendered_quantity = (
            str(int(rework_quantity))
            if float(rework_quantity).is_integer()
            else str(rework_quantity)
        )
        ambiguous = payload.get("ambiguous_operation")
        if not isinstance(ambiguous, dict):
            raise ValueError(
                "manufacturing template lacks ambiguous_operation"
            )
        ambiguous["operation"] = (
            f"submit the prepared {rendered_quantity}-unit corrective Job Card"
        )
    elif instance.family == "erpnext-shared-batch-recovery":
        rework_quantity = instance.fixture["primary_work_order"]["rework_quantity"]
        ambiguous = payload.get("ambiguous_operation")
        if not isinstance(ambiguous, dict):
            raise ValueError("shared-batch template lacks ambiguous_operation")
        ambiguous["operation"] = (
            f"submit the prepared {rework_quantity}-unit corrective Job Card"
        )
    return payload
