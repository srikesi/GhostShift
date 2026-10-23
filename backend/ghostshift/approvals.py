"""Human approval gate for operational actions.

Enforced here, in backend logic — the UI only reflects these rules. An action
can be executed only when every required role has approved it. Executing an
action submits a record to the (simulated) procurement or CMMS provider; it
never stops, isolates or otherwise acts on physical equipment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from .integrations.base import ProcurementProvider, ProviderError, WorkOrderProvider
from .schemas.agents import ActionKind
from .schemas.common import utcnow
from .schemas.workflow import ActionStatus, Decision, DecisionRequest, ProposedAction, RecordStatus
from .state import Store


class GateError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


class ApprovalService:
    def __init__(self, store: Store, procurement: ProcurementProvider, work_orders: WorkOrderProvider,
                 machine_clock: Callable[[str], datetime | None] | None = None):
        self.store = store
        self.procurement = procurement
        self.work_orders = work_orders
        # Replay time for an incident's machine, so activity is stamped in the same clock as the sensors.
        self.machine_clock = machine_clock or (lambda _incident_id: None)

    def _get(self, action_id: str) -> ProposedAction:
        act = self.store.actions.get(action_id)
        if act is None:
            raise GateError(404, "not_found", f"Action '{action_id}' not found")
        return act

    def decide(self, action_id: str, req: DecisionRequest, *, automated: bool = False) -> ProposedAction:
        """Record one role's decision. `automated` is only set by the autopilot policy, never by the API."""
        with self.store.lock:
            act = self._get(action_id)
            if act.status != ActionStatus.awaiting_approval:
                raise GateError(409, "not_awaiting_approval", f"Action is '{act.status.value}', not awaiting approval")
            slot = next((a for a in act.approvals if a.role == req.role), None)
            if slot is None:
                raise GateError(403, "role_not_permitted",
                                f"Role '{req.role.value}' is not a required approver for this action",
                                {"required_roles": [a.role.value for a in act.approvals]})
            if slot.decision != Decision.pending:
                raise GateError(409, "already_decided", f"Role '{req.role.value}' already {slot.decision.value} this action")
            if req.decision == "approve" and act.requires_isolation_attestation and not req.isolation_attestation:
                raise GateError(422, "isolation_attestation_required",
                                "Confirm the lockout/tagout checkbox to approve physical work")
            now = utcnow()
            slot.decision = Decision.approved if req.decision == "approve" else Decision.rejected
            slot.decided_by, slot.decided_at, slot.note = req.approver_name, now, req.note
            slot.automated = automated
            if req.decision == "approve" and act.requires_isolation_attestation:
                act.isolation_attested_by = req.approver_name
            if slot.decision == Decision.rejected:
                act.status = ActionStatus.rejected
                self._set_target_status(act, RecordStatus.rejected)
            elif all(a.decision == Decision.approved for a in act.approvals):
                act.status = ActionStatus.approved
            act.updated_at = now
            verb = "approved" if slot.decision == Decision.approved else "rejected"
            self._log(act, "policy" if automated else "person", req.approver_name, f"decision_{verb}",
                      f"{verb.capitalize()} {self._describe(act)}" + (f": {req.note}" if req.note else ""))
            return act

    def execute(self, action_id: str, *, actor: str = "person", actor_name: str = "Supervisor") -> ProposedAction:
        with self.store.lock:
            act = self._get(action_id)
            if act.status != ActionStatus.approved or not all(a.decision == Decision.approved for a in act.approvals):
                raise GateError(409, "approval_required",
                                f"Action is '{act.status.value}'; all required approvals must be granted before execution",
                                {"pending_roles": [a.role.value for a in act.approvals if a.decision != Decision.approved]})
            try:
                if act.kind == ActionKind.submit_requisition:
                    req = self.store.requisitions[act.target_id]
                    result = self.procurement.submit_requisition(requisition_id=req.id, sku=req.sku, quantity=req.quantity)
                    provider = self.procurement.info
                else:
                    wo = self.store.work_orders[act.target_id]
                    result = self.work_orders.dispatch(work_order_id=wo.id, title=wo.title, machine_id=wo.machine_id)
                    provider = self.work_orders.info
            except ProviderError as exc:
                act.status, act.result_note, act.updated_at = ActionStatus.failed, str(exc), utcnow()
                raise GateError(502, "provider_failure", str(exc)) from exc
            act.status = ActionStatus.completed_simulated if result.simulated else ActionStatus.completed
            act.external_reference, act.result_note, act.provider = result.external_reference, result.note, provider
            act.updated_at = utcnow()
            self._set_target_status(act, RecordStatus.submitted_simulated if result.simulated else RecordStatus.submitted,
                                    result.external_reference)
            sent = "Placed" if act.kind == ActionKind.submit_requisition else "Released"
            self._log(act, actor, actor_name, "executed",
                      f"{sent} {self._describe(act)} ({result.external_reference}{', simulated' if result.simulated else ''})")
            return act

    def _describe(self, act: ProposedAction) -> str:
        if act.kind == ActionKind.submit_requisition:
            req = self.store.requisitions.get(act.target_id)
            cost = f", ${req.estimated_cost_usd:,.0f}" if req and req.estimated_cost_usd is not None else ""
            return f"order for {req.sku}{cost}" if req else "parts order"
        return f"work order {act.target_id}"

    def _log(self, act: ProposedAction, actor: str, actor_name: str, kind: str, text: str) -> None:
        self.store.log(act.incident_id, actor, actor_name, kind, text, self.machine_clock(act.incident_id))

    def _set_target_status(self, act: ProposedAction, status: RecordStatus, ref: str | None = None) -> None:
        table = self.store.requisitions if act.kind == ActionKind.submit_requisition else self.store.work_orders
        rec = table.get(act.target_id)
        if rec is not None:
            rec.status = status
            if ref:
                rec.external_reference = ref
