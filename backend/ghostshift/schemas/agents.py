"""Typed input/output contracts for each workflow stage."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import Contract, Provenance, Severity
from .machine import ComponentHealth, Machine
from .telemetry import TelemetryWindow

# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


class Baseline(Contract):
    start_index: int
    end_index: int
    mean: float
    std: float
    n: int


class LimitState(str, Enum):
    normal = "normal"
    alert = "alert"
    danger = "danger"
    no_limits = "no_limits"


class EvidenceRef(Contract):
    id: str
    sensor_id: str
    start_index: int
    end_index: int
    start_time: datetime
    end_time: datetime
    description: str


class SensorAssessment(Contract):
    sensor_id: str
    sensor_name: str
    component_id: str
    unit: str
    role: str
    baseline: Baseline
    recent_mean: float
    current_value: float = Field(description="Mean of the last 3 samples; used for alarm-limit checks")
    latest_value: float
    z_score: float
    pct_change: float
    slope_per_hour: float
    limit_state: LimitState
    alert_limit: float | None
    danger_limit: float | None
    anomalous: bool
    severity: Severity
    missing_points: int


class Anomaly(Contract):
    sensor_id: str
    component_id: str
    severity: Severity
    description: str
    evidence_id: str


class FaultHypothesis(Contract):
    fault_mode_id: str
    name: str
    component_id: str
    signature_sensor_ids: list[str] = Field(description="Sensors whose deviation defines the signature")
    confidence: float = Field(ge=0, le=1)
    confidence_method: str
    matched_conditions: list[str]
    unmatched_conditions: list[str]
    contradicting_conditions: list[str]


class DiagnosticsInput(Contract):
    machine: Machine
    window: TelemetryWindow
    baseline_start_index: int
    baseline_end_index: int
    recent_points: int = 8


class DiagnosticsResult(Contract):
    machine_id: str
    analyzed_start_index: int
    analyzed_end_index: int
    severity: Severity
    sensors: list[SensorAssessment]
    anomalies: list[Anomaly]
    hypotheses: list[FaultHypothesis]
    evidence: list[EvidenceRef]
    warnings: list[str]
    method: str
    provenance: Provenance


# ---------------------------------------------------------------------------
# Prognostics
# ---------------------------------------------------------------------------


class FailureRisk(Contract):
    score: float = Field(ge=0, le=1)
    band: str = Field(description="low | moderate | high | severe")
    horizon_hours: float
    calibrated: bool = Field(description="False: heuristic score, not a validated probability")
    definition: str


class RulEstimate(Contract):
    component_id: str
    sensor_id: str | None
    supportable: bool
    value_hours: float | None
    lower_hours: float | None
    upper_hours: float | None
    unit: str = "hours"
    threshold: float | None
    method: str
    confidence_note: str
    limitations: list[str]
    provenance: Provenance


class PrognosticsInput(Contract):
    machine: Machine
    window: TelemetryWindow
    diagnostics: DiagnosticsResult
    as_of: datetime
    trend_points: int = 24
    risk_horizon_hours: float = 24.0


class PrognosticsResult(Contract):
    machine_id: str
    affected_component_id: str | None
    failure_risk: FailureRisk
    rul: RulEstimate | None
    component_health: list[ComponentHealth]
    method: str
    limitations: list[str]
    provenance: Provenance


# ---------------------------------------------------------------------------
# Safety supervisor
# ---------------------------------------------------------------------------


class RiskTier(str, Enum):
    routine = "routine"
    elevated = "elevated"
    high = "high"
    critical = "critical"


class ApproverRole(str, Enum):
    maintenance_supervisor = "maintenance_supervisor"
    operations_manager = "operations_manager"


class ActionKind(str, Enum):
    submit_requisition = "submit_requisition"
    dispatch_work_order = "dispatch_work_order"


class ApprovalPolicy(Contract):
    action_kind: ActionKind
    roles: list[ApproverRole]
    requires_isolation_attestation: bool
    reason: str


class SafetyInput(Contract):
    diagnostics: DiagnosticsResult
    prognostics: PrognosticsResult
    estimated_requisition_cost: float | None = None


class SafetyAssessment(Contract):
    risk_tier: RiskTier
    rationale: list[str]
    escalation: list[str]
    recommended_response: str
    notify_technician: bool
    required_approvals: list[ApprovalPolicy]
    safety_notices: list[str]
    policy_version: str


# ---------------------------------------------------------------------------
# Maintenance & supply
# ---------------------------------------------------------------------------


class Availability(Contract):
    on_hand: int | None
    lead_time_days: float | None
    location: str | None
    provenance: Provenance


class PartCandidate(Contract):
    sku: str
    description: str
    manufacturer_part_number: str
    unit_cost_usd: float | None
    cost_provenance: Provenance
    match_score: float = Field(ge=0, le=1)
    match_rationale: list[str]
    availability: Availability


class MaintenanceWindow(Contract):
    start: datetime
    end: datetime
    label: str
    rationale: str
    before_rul_lower_bound: bool | None
    provenance: Provenance


class WorkOrderTask(Contract):
    step: int
    description: str
    requires_qualified_person: bool = False


class WorkOrderDraft(Contract):
    title: str
    machine_id: str
    component_id: str
    fault_mode_id: str | None
    priority: str
    tasks: list[WorkOrderTask]
    estimated_duration_hours: float
    required_skills: list[str]
    safety_references: list[str]


class MaintenanceInput(Contract):
    machine: Machine
    diagnostics: DiagnosticsResult
    prognostics: PrognosticsResult
    safety: SafetyAssessment
    as_of: datetime


class MaintenanceProposal(Contract):
    component_id: str
    fault_mode_id: str | None
    proposed_part: PartCandidate | None
    alternatives: list[PartCandidate]
    quantity: int
    estimated_cost_usd: float | None
    maintenance_window: MaintenanceWindow | None
    work_order: WorkOrderDraft
    next_steps: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Narrative (optional LLM explanation; never changes safety outputs)
# ---------------------------------------------------------------------------


class NarrativeInput(Contract):
    machine_name: str
    machine_id: str
    component_name: str
    fault_name: str | None
    risk_tier: RiskTier
    key_findings: list[str]
    rul_text: str
    recommended_response: str
    sms_finding: str = Field(max_length=90, description="Deterministic ASCII key finding for SMS")


class IncidentNarrative(Contract):
    headline: str = Field(min_length=8, max_length=110)
    summary: str = Field(min_length=20, max_length=900)
    technician_brief: str = Field(min_length=10, max_length=400)
    sms_key_finding: str = Field(min_length=5, max_length=90)
