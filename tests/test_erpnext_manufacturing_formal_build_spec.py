from __future__ import annotations

import unittest
from pathlib import Path

from aftermath_bench.erpnext_manufacturing_formal_build_spec import (
    MANUFACTURING_FORMAL_PROFILE,
)
from aftermath_bench.erpnext_formal_build_spec import _value_at_path
from aftermath_bench.integrations.erpnext_manufacturing_agent import (
    ERPNextManufacturingEnvironment,
)
from aftermath_bench.native_erpnext_manufacturing_family import (
    ERP_NEXT_MANUFACTURING_TOOLS,
)
from aftermath_bench.release_manifest import TRUSTED_FORMAL_EVALUATORS


class ERPNextManufacturingFormalBuildSpecTests(unittest.TestCase):
    def test_profile_binds_the_model_surface_failure_to_native_attempt(self) -> None:
        raw_boundary = {
            "surface_error": "connection_lost_before_confirmation",
            "latest_attempt": {
                "result": {
                    "ok": False,
                    "error": "connection_lost_before_confirmation",
                    "exception_type": "RemoteDisconnected",
                }
            },
        }
        self.assertEqual(
            _value_at_path(
                raw_boundary,
                MANUFACTURING_FORMAL_PROFILE.raw_surface_failure_path,
            ),
            raw_boundary["latest_attempt"]["result"],
        )

    def test_profile_matches_the_exact_public_tool_surface(self) -> None:
        self.assertEqual(
            tuple(tool.name for tool in ERP_NEXT_MANUFACTURING_TOOLS),
            ERPNextManufacturingEnvironment.TOOL_NAMES,
        )
        self.assertEqual(
            tuple(tool.name for tool in MANUFACTURING_FORMAL_PROFILE.tool_definitions),
            MANUFACTURING_FORMAL_PROFILE.environment_tool_names,
        )
        self.assertFalse(
            any(
                name.startswith("repair_")
                for name in MANUFACTURING_FORMAL_PROFILE.environment_tool_names
            )
        )

    def test_all_profile_sources_exist_and_evaluator_is_trusted(self) -> None:
        paths = (
            MANUFACTURING_FORMAL_PROFILE.tool_definition_source,
            MANUFACTURING_FORMAL_PROFILE.tool_implementation_source,
            MANUFACTURING_FORMAL_PROFILE.evaluator_source,
            *MANUFACTURING_FORMAL_PROFILE.tool_implementation_dependencies,
            *MANUFACTURING_FORMAL_PROFILE.native_runtime_contract_sources,
            *MANUFACTURING_FORMAL_PROFILE.boundary_contract_sources,
        )
        self.assertTrue(paths)
        for value in paths:
            self.assertTrue(Path(value).is_file(), value)
        self.assertIs(
            TRUSTED_FORMAL_EVALUATORS[MANUFACTURING_FORMAL_PROFILE.family_id],
            MANUFACTURING_FORMAL_PROFILE.evaluator,
        )

    def test_terminal_queue_rows_are_excluded_but_pending_rows_are_bound(self) -> None:
        project = MANUFACTURING_FORMAL_PROFILE.boundary_state_projection
        state = {
            "work_order": {"status": "In Process"},
            "rq_jobs": [
                {"name": "done", "status": "finished"},
                {"name": "pending", "status": "queued"},
            ],
        }
        self.assertEqual(
            project(state)["rq_jobs"],
            [{"name": "pending", "status": "queued"}],
        )


if __name__ == "__main__":
    unittest.main()
