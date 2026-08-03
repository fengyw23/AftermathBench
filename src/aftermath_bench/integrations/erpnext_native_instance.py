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
    return payload
