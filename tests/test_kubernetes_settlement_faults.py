from __future__ import annotations

import unittest
from unittest.mock import Mock

from aftermath_bench.integrations.kubernetes_settlement_faults import (
    KUBERNETES_SETTLEMENT_VARIANTS,
    SURFACE_ERROR,
    KubernetesSettlementFaultBoundary,
)
from aftermath_bench.integrations.kubernetes_settlement_prefix import (
    SETTLEMENT_TAINT_KEY,
)


class KubernetesSettlementFaultBoundaryTest(unittest.TestCase):
    def _api(self) -> Mock:
        api = Mock()
        api.create.return_value = {
            "kind": "Job",
            "metadata": {"name": "settlement-2026-07-x7k2p"},
        }
        api.list.side_effect = lambda resource, **_kwargs: (
            [{"metadata": {"name": "node-1"}}]
            if resource == "nodes"
            else [{"status": {"phase": "Pending"}}]
            if resource == "pods"
            else []
        )
        return api

    def test_every_variant_exposes_the_same_surface_error(self) -> None:
        for variant in KUBERNETES_SETTLEMENT_VARIANTS:
            with self.subTest(variant=variant):
                api = self._api()
                boundary = KubernetesSettlementFaultBoundary(api)
                with self.assertRaisesRegex(ConnectionError, SURFACE_ERROR):
                    boundary.trigger(variant)

    def test_not_reached_performs_no_write(self) -> None:
        api = self._api()
        boundary = KubernetesSettlementFaultBoundary(api)
        with self.assertRaises(ConnectionError):
            boundary.trigger("job_create_request_not_reached")
        api.create.assert_not_called()
        api.taint_node.assert_not_called()

    def test_completed_state_waits_for_native_job_completion(self) -> None:
        api = self._api()
        boundary = KubernetesSettlementFaultBoundary(api)
        with self.assertRaises(ConnectionError):
            boundary.trigger("job_created_response_lost")
        api.create.assert_called_once()
        api.wait_condition.assert_called_once()

    def test_pending_state_uses_a_visible_node_taint(self) -> None:
        api = self._api()
        boundary = KubernetesSettlementFaultBoundary(api)
        with self.assertRaises(ConnectionError):
            boundary.trigger("job_created_pod_pending")
        taint = api.taint_node.call_args.args[1]
        self.assertIn(SETTLEMENT_TAINT_KEY, taint)


if __name__ == "__main__":
    unittest.main()
