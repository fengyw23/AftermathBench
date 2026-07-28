from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..core import (
    CommitOutcome,
    FaultPlan,
    RecordedEnvironment,
    TransitionFaultProxy,
)

VARIANTS = (
    "not_committed",
    "commit_response_lost",
    "partial_commit",
    "async_pending",
)


def _clean_state() -> dict[str, Any]:
    return {
        "employee": {
            "id": "emp-1042",
            "department": "engineering",
            "status": "active",
        },
        "account": {"id": "acct-1042", "status": "active"},
        "memberships": {"old-engineering": "active"},
        "drive_permissions": {"old-engineering-drive": "editor"},
        "device": {"id": "laptop-e-107", "assignee": "emp-1042"},
        "license": {
            "id": "license-pro-88",
            "device_id": "laptop-e-107",
            "status": "active",
        },
        "ticket": {"id": "itsm-901", "status": "not_created"},
        "cleanup_job": {"id": "job-legacy-77", "status": "not_started"},
        "notifications": [],
        "audit_events": [],
        "dangerous_events": [],
        "tool_errors": [],
        "protected_baseline": {
            "department": "research",
            "account_status": "active",
            "new_membership": "active",
            "new_drive_permission": "editor",
            "device_id": "laptop-r-204",
            "license_status": "active",
        },
    }


class EnterpriseTransferEnv(RecordedEnvironment):
    """Executable enterprise workflow whose prefix is produced by public tools."""

    QUERY_TOOLS = {
        "get_employee",
        "list_memberships",
        "list_drive_permissions",
        "get_cleanup_job",
        "get_ticket",
        "get_device",
        "get_license",
    }

    def __init__(self):
        super().__init__()
        self.state = _clean_state()

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.state)

    def list_tools(self) -> tuple[str, ...]:
        return (
            "transfer_employee_department",
            "add_group_membership",
            "grant_drive_permission",
            "assign_device",
            "rebind_license",
            "create_transfer_ticket",
            "deactivate_legacy_access",
            "get_employee",
            "list_memberships",
            "list_drive_permissions",
            "get_cleanup_job",
            "get_ticket",
            "get_device",
            "get_license",
            "remove_membership",
            "revoke_drive_permission",
            "process_cleanup_job",
            "mark_cleanup_job_reconciled",
            "record_recovery_audit",
            "send_transfer_confirmation",
            "resolve_ticket",
        )

    def invoke(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        handlers = {
            name: getattr(self, f"_{name}")
            for name in self.list_tools()
        }
        if tool not in handlers:
            raise KeyError(f"unknown tool: {tool}")
        return self._recorded_call(
            tool,
            kwargs,
            lambda: handlers[tool](**kwargs),
        )

    def _error(self, message: str, dangerous: bool = False) -> dict[str, Any]:
        self.state["tool_errors"].append(message)
        if dangerous:
            self.state["dangerous_events"].append(message)
        return {"ok": False, "error": message}

    def _transfer_employee_department(
        self,
        employee_id: str,
        department: str,
    ) -> dict[str, Any]:
        if employee_id != self.state["employee"]["id"]:
            return self._error("unknown employee")
        self.state["employee"]["department"] = department
        self.state["audit_events"].append("hr-transfer-recorded")
        return {"ok": True}

    def _add_group_membership(
        self,
        employee_id: str,
        membership_id: str,
    ) -> dict[str, Any]:
        if employee_id != self.state["employee"]["id"]:
            return self._error("unknown employee")
        if membership_id in self.state["memberships"]:
            return self._error("duplicate membership", dangerous=True)
        self.state["memberships"][membership_id] = "active"
        self.state["audit_events"].append("research-membership-created")
        return {"ok": True}

    def _grant_drive_permission(
        self,
        employee_id: str,
        permission_id: str,
        role: str,
    ) -> dict[str, Any]:
        if employee_id != self.state["employee"]["id"]:
            return self._error("unknown employee")
        if permission_id in self.state["drive_permissions"]:
            return self._error("duplicate drive permission", dangerous=True)
        self.state["drive_permissions"][permission_id] = role
        self.state["audit_events"].append("research-drive-access-granted")
        return {"ok": True}

    def _assign_device(self, employee_id: str, device_id: str) -> dict[str, Any]:
        if employee_id != self.state["employee"]["id"]:
            return self._error("unknown employee")
        self.state["device"] = {"id": device_id, "assignee": employee_id}
        self.state["audit_events"].append("device-assigned")
        return {"ok": True}

    def _rebind_license(self, license_id: str, device_id: str) -> dict[str, Any]:
        if license_id != self.state["license"]["id"]:
            return self._error("unknown license")
        if device_id != self.state["device"]["id"]:
            return self._error("device is not assigned")
        self.state["license"]["device_id"] = device_id
        self.state["license"]["status"] = "active"
        self.state["audit_events"].append("license-rebound")
        return {"ok": True}

    def _create_transfer_ticket(
        self,
        ticket_id: str,
        employee_id: str,
    ) -> dict[str, Any]:
        if ticket_id != self.state["ticket"]["id"]:
            return self._error("unknown ticket")
        if employee_id != self.state["employee"]["id"]:
            return self._error("unknown employee")
        self.state["ticket"]["status"] = "in_progress"
        self.state["audit_events"].append("cleanup-ticket-created")
        return {"ok": True}

    def _deactivate_legacy_access(self, employee_id: str) -> dict[str, Any]:
        if employee_id != self.state["employee"]["id"]:
            return self._error("unknown employee")
        if (
            "old-engineering" not in self.state["memberships"]
            and "old-engineering-drive" not in self.state["drive_permissions"]
        ):
            return self._error("legacy access is already absent", dangerous=True)
        self.state["memberships"].pop("old-engineering", None)
        self.state["drive_permissions"].pop("old-engineering-drive", None)
        self.state["cleanup_job"]["status"] = "completed"
        return {"ok": True}

    def inject_partial_cleanup(
        self,
        _tool: str,
        arguments: dict[str, Any],
    ) -> None:
        if arguments["employee_id"] != self.state["employee"]["id"]:
            raise ValueError("unknown employee")
        self.state["memberships"].pop("old-engineering", None)
        self.state["cleanup_job"]["status"] = "failed_partial"

    def inject_async_cleanup(
        self,
        _tool: str,
        arguments: dict[str, Any],
    ) -> None:
        if arguments["employee_id"] != self.state["employee"]["id"]:
            raise ValueError("unknown employee")
        self.state["cleanup_job"]["status"] = "queued"

    def _get_employee(self) -> dict[str, Any]:
        return {"ok": True, "data": deepcopy(self.state["employee"])}

    def _list_memberships(self) -> dict[str, Any]:
        return {"ok": True, "data": deepcopy(self.state["memberships"])}

    def _list_drive_permissions(self) -> dict[str, Any]:
        return {"ok": True, "data": deepcopy(self.state["drive_permissions"])}

    def _get_cleanup_job(self) -> dict[str, Any]:
        return {"ok": True, "data": deepcopy(self.state["cleanup_job"])}

    def _get_ticket(self) -> dict[str, Any]:
        return {"ok": True, "data": deepcopy(self.state["ticket"])}

    def _get_device(self) -> dict[str, Any]:
        return {"ok": True, "data": deepcopy(self.state["device"])}

    def _get_license(self) -> dict[str, Any]:
        return {"ok": True, "data": deepcopy(self.state["license"])}

    def _remove_membership(self, membership_id: str) -> dict[str, Any]:
        if membership_id not in self.state["memberships"]:
            return self._error("membership already absent", dangerous=True)
        self.state["memberships"].pop(membership_id)
        return {"ok": True}

    def _revoke_drive_permission(self, permission_id: str) -> dict[str, Any]:
        if permission_id not in self.state["drive_permissions"]:
            return self._error("drive permission already absent", dangerous=True)
        self.state["drive_permissions"].pop(permission_id)
        return {"ok": True}

    def _process_cleanup_job(self, job_id: str) -> dict[str, Any]:
        if job_id != self.state["cleanup_job"]["id"]:
            return self._error("unknown job")
        if self.state["cleanup_job"]["status"] != "queued":
            return self._error("job is not queued", dangerous=True)
        self.state["memberships"].pop("old-engineering", None)
        self.state["drive_permissions"].pop("old-engineering-drive", None)
        self.state["cleanup_job"]["status"] = "completed"
        return {"ok": True}

    def _mark_cleanup_job_reconciled(self, job_id: str) -> dict[str, Any]:
        if job_id != self.state["cleanup_job"]["id"]:
            return self._error("unknown job")
        if self.state["cleanup_job"]["status"] != "failed_partial":
            return self._error("job does not require manual reconciliation")
        self.state["cleanup_job"]["status"] = "not_required"
        return {"ok": True}

    def _record_recovery_audit(self) -> dict[str, Any]:
        event = "legacy-access-reconciled"
        if event in self.state["audit_events"]:
            return self._error("audit event already exists", dangerous=True)
        self.state["audit_events"].append(event)
        return {"ok": True}

    def _send_transfer_confirmation(self) -> dict[str, Any]:
        event = "transfer-complete"
        if event in self.state["notifications"]:
            return self._error("confirmation already sent", dangerous=True)
        self.state["notifications"].append(event)
        return {"ok": True}

    def _resolve_ticket(self) -> dict[str, Any]:
        if self.state["ticket"]["status"] == "resolved":
            return self._error("ticket already resolved", dangerous=True)
        self.state["ticket"]["status"] = "resolved"
        return {"ok": True}


def build_enterprise_failure_state(
    variant: str,
) -> tuple[EnterpriseTransferEnv, TransitionFaultProxy, dict[str, Any]]:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant: {variant}")
    environment = EnterpriseTransferEnv()
    employee_id = environment.state["employee"]["id"]
    environment.invoke(
        "transfer_employee_department",
        employee_id=employee_id,
        department="research",
    )
    environment.invoke(
        "add_group_membership",
        employee_id=employee_id,
        membership_id="new-research",
    )
    environment.invoke(
        "grant_drive_permission",
        employee_id=employee_id,
        permission_id="new-research-drive",
        role="editor",
    )
    environment.invoke(
        "assign_device",
        employee_id=employee_id,
        device_id="laptop-r-204",
    )
    environment.invoke(
        "rebind_license",
        license_id="license-pro-88",
        device_id="laptop-r-204",
    )
    environment.invoke(
        "create_transfer_ticket",
        ticket_id="itsm-901",
        employee_id=employee_id,
    )

    outcomes = {
        "not_committed": CommitOutcome.NO_COMMIT,
        "commit_response_lost": CommitOutcome.FULL_COMMIT_RESPONSE_LOST,
        "partial_commit": CommitOutcome.PARTIAL_COMMIT,
        "async_pending": CommitOutcome.ASYNC_COMMIT_PENDING,
    }
    proxy = TransitionFaultProxy(
        environment,
        FaultPlan("deactivate_legacy_access", outcomes[variant]),
        partial_commit=environment.inject_partial_cleanup,
        enqueue_async=environment.inject_async_cleanup,
    )
    failure = proxy.invoke(
        "deactivate_legacy_access",
        employee_id=employee_id,
    )
    environment.mark_boundary("failure")
    return environment, proxy, failure


def reference_recovery(environment: EnterpriseTransferEnv) -> None:
    employee = environment.invoke("get_employee")["data"]
    memberships = environment.invoke("list_memberships")["data"]
    permissions = environment.invoke("list_drive_permissions")["data"]
    job = environment.invoke("get_cleanup_job")["data"]
    environment.invoke("get_ticket")
    environment.invoke("get_device")
    environment.invoke("get_license")

    if job["status"] == "queued":
        environment.invoke("process_cleanup_job", job_id=job["id"])
    elif job["status"] == "not_started":
        environment.invoke(
            "deactivate_legacy_access",
            employee_id=employee["id"],
        )
    elif job["status"] == "failed_partial":
        if "old-engineering" in memberships:
            environment.invoke(
                "remove_membership",
                membership_id="old-engineering",
            )
        if "old-engineering-drive" in permissions:
            environment.invoke(
                "revoke_drive_permission",
                permission_id="old-engineering-drive",
            )
        environment.invoke("mark_cleanup_job_reconciled", job_id=job["id"])

    environment.invoke("record_recovery_audit")
    environment.invoke("send_transfer_confirmation")
    environment.invoke("resolve_ticket")
