from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import Mock

from aftermath_bench.integrations.kubernetes_settlement_prefix import (
    TARGET_BATCH,
    TARGET_RECEIPT_SHA,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_faults import (
    KUBERNETES_SETTLEMENT_V2_VARIANTS,
    SURFACE_ERROR,
    KubernetesSettlementV2FaultBoundary,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_prefix import (
    AUDIT_CONFIGMAP,
    PRIOR_AUDIT_DELIVERY_KEY,
    TARGET_AUDIT_DELIVERY_KEY,
    orchestrated_prefix_manifests,
)
from aftermath_bench.integrations.kubernetes_settlement_v2_recovery import (
    evaluate_kubernetes_settlement_v2_recovery,
)
from aftermath_bench.schema import repository_root
from test_kubernetes_settlement_recovery import _passing_evidence


class KubernetesSettlementV2BlueprintTest(unittest.TestCase):
    def test_all_scored_obligations_are_visible(self) -> None:
        path = (
            repository_root()
            / "data"
            / "scenario_blueprints"
            / "k8s-settlement-orchestrated-dev-002"
            / "scenario.json"
        )
        scenario = json.loads(path.read_text(encoding="utf-8"))
        instruction = scenario["user_instruction"]
        for term in (
            "exactly one completed Kubernetes Job",
            "Lease",
            "exactly one durable settlement receiver delivery",
            "exactly one durable audit receiver event",
            "approved receipt",
            "settlement-ledger",
            "settlement-audit",
            "last completed batch",
        ):
            self.assertIn(term, instruction)
        self.assertEqual(len(scenario["matched_variants"]), 4)

    def test_prefix_exposes_audit_and_status_vocabulary(self) -> None:
        manifests = orchestrated_prefix_manifests()
        audit = next(
            item
            for item in manifests
            if item["kind"] == "ConfigMap"
            and item["metadata"].get("name") == AUDIT_CONFIGMAP
        )
        policy = next(
            item
            for item in manifests
            if item["kind"] == "ConfigMap"
            and item["metadata"].get("name") == "settlement-policy"
        )
        self.assertEqual(audit["data"]["2026-06.status"], "recorded")
        self.assertEqual(policy["data"]["receiptStatus"], "approved")
        self.assertEqual(policy["data"]["auditStatus"], "recorded")


class KubernetesSettlementV2FaultTest(unittest.TestCase):
    def _api(self) -> Mock:
        api = Mock()
        api.create.return_value = {
            "metadata": {"name": "settlement-2026-07-abc", "uid": "job-uid"}
        }
        return api

    def test_all_variants_share_one_surface_error(self) -> None:
        for variant in KUBERNETES_SETTLEMENT_V2_VARIANTS:
            with self.subTest(variant=variant):
                api = self._api()
                request = Mock(return_value={"attempt_count": 1})
                boundary = KubernetesSettlementV2FaultBoundary(
                    api, json_request=request
                )
                with self.assertRaisesRegex(ConnectionError, SURFACE_ERROR):
                    boundary.trigger(variant)

    def test_downstream_states_are_independently_partial(self) -> None:
        api = self._api()
        request = Mock(return_value={"attempt_count": 1})
        boundary = KubernetesSettlementV2FaultBoundary(api, json_request=request)
        with self.assertRaises(ConnectionError):
            boundary.trigger("job_suspended_partial_records")
        self.assertEqual(api.apply.call_count, 2)
        self.assertEqual(request.call_count, 1)
        self.assertIn("audit:settlement-2026-07", request.call_args.kwargs["headers"].values())

        api = self._api()
        request = Mock(return_value={"attempt_count": 1})
        boundary = KubernetesSettlementV2FaultBoundary(api, json_request=request)
        with self.assertRaises(ConnectionError):
            boundary.trigger("delivery_committed_response_lost")
        self.assertEqual(api.apply.call_count, 2)
        request.assert_called_once()
        api.patch.assert_called_once()


class KubernetesSettlementV2EvaluationTest(unittest.TestCase):
    def _passing(self) -> dict:
        evidence = copy.deepcopy(_passing_evidence())
        target = next(
            job
            for job in evidence["jobs"]
            if job["metadata"]["labels"]["batch"] == TARGET_BATCH
        )
        target["metadata"]["uid"] = "job-uid-2026-07"
        evidence["configmaps"].append(
            {
                "metadata": {"name": AUDIT_CONFIGMAP},
                "data": {
                    "2026-07.batch": TARGET_BATCH,
                    "2026-07.status": "recorded",
                    "2026-07.receipt_sha256": TARGET_RECEIPT_SHA,
                    "2026-07.job_uid": "job-uid-2026-07",
                },
            }
        )
        evidence["cronjobs"][0]["metadata"]["annotations"] = {
            "aftermath.dev/last-completed-batch": TARGET_BATCH
        }
        evidence["external_deliveries"].extend(
            [
                {
                    "key": PRIOR_AUDIT_DELIVERY_KEY,
                    "attempt_count": 1,
                    "payload": {"batch": "settlement-2026-06"},
                },
                {
                    "key": TARGET_AUDIT_DELIVERY_KEY,
                    "attempt_count": 1,
                    "payload": {
                        "batch": TARGET_BATCH,
                        "job_uid": "job-uid-2026-07",
                        "status": "accepted",
                    },
                },
            ]
        )
        return evidence

    def test_complete_orchestrated_state_passes(self) -> None:
        report = evaluate_kubernetes_settlement_v2_recovery(self._passing())
        self.assertTrue(report.passed, report.failures)

    def test_pending_audit_or_missing_marker_fails_completeness(self) -> None:
        evidence = self._passing()
        evidence["configmaps"][-1]["data"]["2026-07.status"] = "pending"
        evidence["cronjobs"][0]["metadata"]["annotations"] = {}
        report = evaluate_kubernetes_settlement_v2_recovery(evidence)
        self.assertFalse(report.passed)
        self.assertFalse(report.components["repair_completeness"])
        self.assertFalse(report.checks["audit_record_closed"])
        self.assertFalse(report.checks["schedule_completion_marker_updated"])


if __name__ == "__main__":
    unittest.main()
