"""Workflow runs, incidents, actions/approvals, records and notifications."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from .agents import (
    ActionKind,
    ApproverRole,
    DiagnosticsResult,
    IncidentNarrative,
    MaintenanceProposal,
    PrognosticsResult,
    SafetyAssessment,
)
from .common import Contract, ProviderInfo, Severity, StageStatus
from .machine import Component, ComponentHealth


class StageRecord(Contract):
    name: str
    status: StageStatus
    provider: ProviderInfo
    started_at: datetime
    duration_ms: float
    attempts: int = 1
    error: str | None = None
    fallback_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)


class WorkflowStatus(str, Enum):
    completed = "completed"  # incident created / updated and nothing awaits approval
    completed_no_incident = "completed_no_incident"
    awaiting_approval = "awaiting_approval"
    failed = "failed"


class WorkflowRun(Contract):
    id: str
    machine_id: str
    trigger: Literal["manual", "replay_monitor"]
    mode: str
    analyzed_start_index: int
    analyzed_end_index: int
    status: WorkflowStatus
    stages: list[StageRecord]
    incident_id: str | None
    created_at: datetime
    completed_at: datetime | None
    error: str | None = None


class ActionStatus(str, Enum):
    awaiting_approval = "awaiting_approval"
    approved = "approved"
    rejected = "rejected"
    completed_simulated = "completed_simulated"
    completed = "completed"  # real external system confirmed
    failed = "failed"


class Decision(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApprovalRecord(Contract):
    role: ApproverRole
    decision: Decision = Decision.pending
    decided_by: str | None = None
    decided_at: datetime | None = None
    note: str | None = None
    automated: bool = Field(default=False, description="Decided by the autopilot policy, not a person")


class ProposedAction(Contract):
    id: str
    incident_id: str
    kind: ActionKind
    title: str
    target_id: str = Field(description="Requisition or work-order id this action submits")
    status: ActionStatus
    approvals: list[ApprovalRecord]
    requires_isolation_attestation: bool
    isolation_attested_by: str | None = None
    external_reference: str | None = None
    result_note: str | None = None
    provider: ProviderInfo | None = None
    created_at: datetime
    updated_at: datetime


class DecisionRequest(Contract):
    role: ApproverRole
    approver_name: str = Field(min_length=2, max_length=80)
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)
    isolation_attestation: bool = Field(
        default=False,
        description=(
            "Approver confirms isolation (LOTO) will be performed and verified by qualified "
            "personnel under site procedure. This attests to a plan; it does not isolate anything."
        ),
    )


class RecordStatus(str, Enum):
    draft = "draft"
    awaiting_approval = "awaiting_approval"
    submitted_simulated = "submitted_simulated"
    submitted = "submitted"
    rejected = "rejected"


class Requisition(Contract):
    id: str
    incident_id: str
    sku: str
    description: str
    quantity: int
    estimated_cost_usd: float | None
    status: RecordStatus
    simulated: bool
    external_reference: str | None = None
    created_at: datetime


class WorkOrder(Contract):
    id: str
    incident_id: str
    machine_id: str
    component_id: str
    title: str
    priority: str
    status: RecordStatus
    simulated: bool
    window_start: datetime | None
    window_end: datetime | None
    external_reference: str | None = None
    created_at: datetime


class NotificationStatus(str, Enum):
    simulated_sent = "simulated_sent"
    sent = "sent"  # accepted by the provider; delivery not yet confirmed
    delivered = "delivered"  # the carrier confirmed delivery
    failed = "failed"
    skipped = "skipped"


class Notification(Contract):
    id: str
    incident_id: str
    channel: Literal["sms"]
    recipient_label: str
    to_masked: str
    body: str
    inspection_url: str
    status: NotificationStatus
    provider: ProviderInfo
    attempts: int
    error: str | None = None
    external_id: str | None = None
    created_at: datetime


class Incident(Contract):
    id: str
    machine_id: str
    status: Literal["open", "closed"]
    severity: Severity
    affected_component_id: str | None
    fault_mode_id: str | None
    created_at: datetime
    updated_at: datetime
    run_ids: list[str]
    diagnostics: DiagnosticsResult
    prognostics: PrognosticsResult
    safety: SafetyAssessment
    maintenance: MaintenanceProposal | None
    narrative: IncidentNarrative
    narrative_provider: ProviderInfo
    narrative_status: StageStatus
    action_ids: list[str]
    requisition_id: str | None
    work_order_id: str | None
    notification_ids: list[str]


class IncidentView(Contract):
    """Incident with its related records resolved for the dashboard."""

    incident: Incident
    actions: list[ProposedAction]
    requisition: Requisition | None
    work_order: WorkOrder | None
    notifications: list[Notification]
    latest_run: WorkflowRun | None
    activity: list["ActivityEvent"] = Field(default_factory=list)


class ComponentWithHealth(Contract):
    component: Component
    health: ComponentHealth | None


class InspectionView(Contract):
    """Payload for the technician's mobile inspection page (token-scoped)."""

    incident: Incident
    machine_name: str
    machine_id: str
    drawing: str
    components: list[ComponentWithHealth]
    work_order: WorkOrder | None
    expires_at: datetime


class BriefingResponse(Contract):
    incident_id: str
    text: str
    audio_available: bool
    audio_url: str | None
    provider: ProviderInfo
    status: StageStatus
    error: str | None = None


class AutonomyLevel(str, Enum):
    advise = "advise"  # GhostShift drafts everything; people approve every order and work order
    autopilot = "autopilot"  # GhostShift also places parts orders itself, within the policy below


class AutonomySettings(Contract):
    level: AutonomyLevel
    auto_order_limit_usd: float = Field(ge=0, le=100_000)


class AutonomyUpdate(Contract):
    level: AutonomyLevel
    auto_order_limit_usd: float | None = Field(default=None, ge=0, le=100_000)


class ActivityEvent(Contract):
    """One step in an incident's history, and who took it."""

    id: str
    incident_id: str
    at: datetime
    machine_time: datetime | None = Field(description="Replay clock when the step happened")
    actor: Literal["ghostshift", "policy", "person"]
    actor_name: str
    kind: str
    text: str


IncidentView.model_rebuild()
