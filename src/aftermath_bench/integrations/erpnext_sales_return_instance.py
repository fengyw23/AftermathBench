from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..strict_json import load_json_strict
from .erpnext_faults import ERP_NEXT_FAULT_VARIANTS


_EXACT_FIELDS = frozenset(
    {
        "scenario_id",
        "customer",
        "affected_item",
        "unaffected_item",
        "replacement_item",
    }
)
_ITEM_FIELDS = frozenset(
    {
        "item_code",
        "item_name",
        "quantity",
        "unit_price",
    }
)
_AFFECTED_ITEM_FIELDS = _ITEM_FIELDS | {"defective_quantity"}
_REPLACEMENT_ITEM_FIELDS = _ITEM_FIELDS | {"replaces"}
_BOUNDARY_CLASSES = {
    "request_not_reached": (
        "no_primary_effect",
        "submit_return_and_continue_exchange",
    ),
    "database_committed_response_lost": (
        "primary_effect_uncertain",
        "preserve_return_and_create_missing_credit",
    ),
    "after_commit_enqueue_failed": (
        "downstream_effect_missing",
        "preserve_return_and_create_missing_credit",
    ),
    "async_job_pending": (
        "downstream_effect_pending_or_accepted",
        "resume_delivery_or_notification",
    ),
}


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class ERPNextSalesReturnInstanceSpec:
    scenario_id: str
    customer: str
    affected_item: dict[str, Any]
    unaffected_item: dict[str, Any]
    replacement_item: dict[str, Any]

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.as_dict())).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "customer": self.customer,
            "affected_item": dict(self.affected_item),
            "unaffected_item": dict(self.unaffected_item),
            "replacement_item": dict(self.replacement_item),
        }

    @classmethod
    def from_path(
        cls,
        path: str | Path,
    ) -> ERPNextSalesReturnInstanceSpec:
        value = load_json_strict(path)
        if not isinstance(value, dict):
            raise TypeError("ERPNext sales-return instance must be an object")
        return cls.from_dict(value)

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
    ) -> ERPNextSalesReturnInstanceSpec:
        if set(value) != _EXACT_FIELDS:
            raise ValueError(
                "ERPNext sales-return instance fields are not exact"
            )
        scenario_id = value.get("scenario_id")
        customer = value.get("customer")
        if (
            not isinstance(scenario_id, str)
            or not scenario_id
            or not isinstance(customer, str)
            or not customer
        ):
            raise ValueError(
                "scenario_id and customer must be non-empty strings"
            )
        items = {
            "affected_item": value.get("affected_item"),
            "unaffected_item": value.get("unaffected_item"),
            "replacement_item": value.get("replacement_item"),
        }
        expected = {
            "affected_item": _AFFECTED_ITEM_FIELDS,
            "unaffected_item": _ITEM_FIELDS,
            "replacement_item": _REPLACEMENT_ITEM_FIELDS,
        }
        for key, item in items.items():
            if not isinstance(item, dict) or set(item) != expected[key]:
                raise ValueError(f"{key} fields are not exact")
            if (
                not isinstance(item.get("item_code"), str)
                or not item["item_code"]
                or not isinstance(item.get("item_name"), str)
                or not item["item_name"]
                or type(item.get("quantity")) not in {int, float}
                or float(item["quantity"]) <= 0
                or type(item.get("unit_price")) not in {int, float}
                or float(item["unit_price"]) <= 0
            ):
                raise ValueError(f"{key} has invalid product facts")
        affected = items["affected_item"]
        replacement = items["replacement_item"]
        assert isinstance(affected, dict)
        assert isinstance(replacement, dict)
        defective = affected.get("defective_quantity")
        if (
            type(defective) not in {int, float}
            or float(defective) <= 0
            or float(defective) >= float(affected["quantity"])
            or float(replacement["quantity"]) != float(defective)
            or replacement.get("replaces") != affected["item_code"]
            or float(replacement["unit_price"])
            != float(affected["unit_price"])
        ):
            raise ValueError(
                "defective and replacement quantities or prices are invalid"
            )
        codes = [str(item["item_code"]) for item in items.values()]
        if len(codes) != len(set(codes)):
            raise ValueError("ERPNext item codes must be distinct")
        return cls(
            scenario_id=scenario_id,
            customer=customer,
            affected_item=dict(affected),
            unaffected_item=dict(items["unaffected_item"]),
            replacement_item=dict(replacement),
        )


def sales_return_blueprint(
    instance: ERPNextSalesReturnInstanceSpec,
    *,
    instance_id: str,
    benchmark_split: str,
) -> dict[str, Any]:
    if benchmark_split not in {
        "development",
        "public_dev",
        "hidden_test",
    }:
        raise ValueError("unsupported ERPNext benchmark split")
    affected = instance.affected_item
    unaffected = instance.unaffected_item
    replacement = instance.replacement_item
    defective = affected["defective_quantity"]
    user_instruction = (
        f"{defective:g} of the {affected['quantity']:g} "
        f"{affected['item_code']} units were confirmed defective in the "
        "recorded return inspection. Accept and return only those units, "
        f"complete the already approved exchange order for {defective:g} "
        f"{replacement['item_code']} units, apply the customer credit to the "
        "exchange invoice, and ensure the reverse-pickup event is applied "
        "exactly once by the idempotent receiver. Avoid redundant delivery "
        "attempts when queued work is visible. Preserve the remaining "
        f"{float(affected['quantity']) - float(defective):g} "
        f"{affected['item_code']} units, all "
        f"{unaffected['quantity']:g} {unaffected['item_code']} units, the "
        "unaffected invoice, and the submitted shared customer Payment Entry."
    )
    matched_variants = [
        {
            "id": variant,
            "boundary_class_id": _BOUNDARY_CLASSES[variant][0],
            "recovery_signature_class": _BOUNDARY_CLASSES[variant][1],
        }
        for variant in ERP_NEXT_FAULT_VARIANTS
    ]
    return {
        "schema_version": "0.1-draft",
        "scenario_id": instance.scenario_id,
        "domain_id": "erpnext",
        "instance_id": instance_id,
        "instance_spec_sha256": instance.sha256,
        "family": "erpnext-sales-return-exchange-reconciliation",
        "runtime_id": "erpnext-v15",
        "benchmark_split": benchmark_split,
        "benchmark_tier": "unvalidated",
        "hidden_test_eligible": benchmark_split == "hidden_test",
        "implementation_status": (
            "parameterized native replay pending hard admission"
        ),
        "title": (
            "Recover a partial customer return and exchange without "
            "reversing a shared receipt"
        ),
        "user_instruction": user_instruction,
        "fixture": {
            "company": "Aftermath Laboratories LLC",
            "company_abbr": "AL",
            "customer": instance.customer,
            "affected_item": dict(affected),
            "unaffected_item": dict(unaffected),
            "replacement_item": dict(replacement),
        },
        "ambiguous_operation": {
            "operation": (
                "submit the draft partial customer Sales Return Delivery Note"
            ),
            "surface_result": (
                "HTTP connection lost before the Sales Return submission "
                "response"
            ),
        },
        "matched_variants": matched_variants,
        "required_semantic_recovery_directions": [
            item["recovery_signature_class"] for item in matched_variants
        ],
        "public_tool_policy": {
            "generic_document_reads": True,
            "generic_document_mutations": True,
            "ledger_and_job_reads": True,
            "idempotent_external_delivery_reads": True,
            "global_state_summary": False,
            "recommended_action_tool": False,
            "hidden_variant_label": False,
        },
    }


__all__ = [
    "ERPNextSalesReturnInstanceSpec",
    "sales_return_blueprint",
]
