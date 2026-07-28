from __future__ import annotations

import hashlib
import json

import pytest

from scripts.verify_native_freeze import verify_freeze


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_native_freeze_detects_prefix_drift(tmp_path):
    scenario = tmp_path / "scenario.json"
    prefix = tmp_path / "prefix.json"
    freeze = tmp_path / "freeze.json"
    scenario.write_text(
        json.dumps({"scenario_id": "holdout-001"}),
        encoding="utf-8",
    )
    prefix.write_text(json.dumps({"state": 1}), encoding="utf-8")
    freeze.write_text(
        json.dumps(
            {
                "scenario_id": "holdout-001",
                "scenario_sha256": _sha256(scenario),
                "prefix_sha256": _sha256(prefix),
            }
        ),
        encoding="utf-8",
    )
    assert verify_freeze(
        freeze_path=freeze,
        scenario_path=scenario,
        prefix_path=prefix,
    )["scenario_id"] == "holdout-001"

    prefix.write_text(json.dumps({"state": 2}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not match"):
        verify_freeze(
            freeze_path=freeze,
            scenario_path=scenario,
            prefix_path=prefix,
        )
