from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_BLUEPRINTS = (
    ROOT
    / "data"
    / "scenario_blueprints"
    / "erpnext-manufacturing-rework-dev-001"
    / "scenario.json",
    ROOT
    / "data"
    / "scenario_blueprints"
    / "erpnext-multiwarehouse-transfer-dev-001"
    / "scenario.json",
)
ALLOWED_SHARED_LITERALS = frozenset({"Aftermath Laboratories LLC"})


def _strings(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if len(value) >= 5 else set()
    if isinstance(value, dict):
        return set().union(*(_strings(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_strings(item) for item in value))
    return set()


class ERPNextInstanceIndependenceTests(unittest.TestCase):
    def test_public_fixture_literals_are_not_embedded_in_implementation(self) -> None:
        fixture_literals: set[str] = set()
        for path in PUBLIC_BLUEPRINTS:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fixture_literals.update(_strings(payload["fixture"]))
        fixture_literals -= ALLOWED_SHARED_LITERALS
        implementation = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (ROOT / "src", ROOT / "scripts")
            for path in sorted(root.rglob("*.py"))
        )
        leaked = sorted(
            literal for literal in fixture_literals if literal in implementation
        )
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
