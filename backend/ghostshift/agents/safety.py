"""Safety supervisor: deterministic risk tiering, escalation and approval gates.

These rules are code, not prompts. No LLM output is an input to this agent, and
nothing downstream may lower the tier or remove a required approval.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas.agents import (
    ActionKind,
    ApprovalPolicy,
    ApproverRole,
    LimitState,
    RiskTier,
    SafetyAssessment,
    SafetyInput,
)
from ..schemas.common import Severity

POLICY_VERSION = "ghostshift-safety-policy/1.0"

SAFETY_NOTICES = [
    "GhostShift approvals authorise records and plans only. They do not stop, isolate or make equipment safe.",
    "Physical work requires isolation and verification of zero energy by qualified personnel under the site "
    "lockout/tagout procedure.",
    "Checklists and guidance shown here are reference information, not a substitute for site procedures or OEM instructions.",
]


@dataclass(frozen=True)
class SafetyPolicy:
    critical_rul_lower_h: float = 24.0
    high_rul_lower_h: float = 72.0
    critical_risk: float = 0.9
    high_risk: float = 0.7
    elevated_risk: float = 0.4
    operations_cost_threshold_usd: float = 5000.0


class SafetySupervisor:
    name = "safety_supervisor"

    def __init__(self, policy: SafetyPolicy | None = None):
        self.policy = policy or SafetyPolicy()

    def run(self, inp: SafetyInput) -> SafetyAssessment:
        p = self.policy
        diag, prog = inp.diagnostics, inp.prognostics
        rul = prog.rul
        rul_low = rul.lower_hours if (rul and rul.supportable) else None
        risk = prog.failure_risk.score
        danger = [a for a in diag.sensors if a.limit_state == LimitState.danger and a.role == "health"]
        alert = [a for a in diag.sensors if a.limit_state == LimitState.alert and a.role == "health"]

        rationale: list[str] = []
        if danger:
            rationale += [f"{a.sensor_name.split(' (')[0]} is over its danger limit ({a.current_value:.3g} vs {a.danger_limit:g} {a.unit})" for a in danger]
        if rul_low is not None and rul_low <= p.critical_rul_lower_h:
            rationale.append(f"Could reach the danger limit in {rul_low:.0f} h (under {p.critical_rul_lower_h:g} h)")
        if risk >= p.critical_risk:
            rationale.append(f"Trend uses {risk:.0%} of the safety margin within 24 h")

        if rationale:
            tier = RiskTier.critical
        else:
            if alert:
                rationale += [f"{a.sensor_name.split(' (')[0]} is over its alert limit ({a.current_value:.3g} vs {a.alert_limit:g} {a.unit})" for a in alert]
            if rul_low is not None and rul_low <= p.high_rul_lower_h:
                rationale.append(f"Could reach the danger limit in {rul_low:.0f} h (under {p.high_rul_lower_h:g} h)")
            if risk >= p.high_risk:
                rationale.append(f"Trend uses {risk:.0%} of the safety margin within 24 h")
            if rationale:
                tier = RiskTier.high
            else:
                if diag.severity.rank >= Severity.watch.rank:
                    rationale.append("Readings have moved well outside their normal range")
                if risk >= p.elevated_risk:
                    rationale.append(f"Trend uses {risk:.0%} of the safety margin within 24 h")
                tier = RiskTier.elevated if rationale else RiskTier.routine
        if tier == RiskTier.routine:
            rationale.append("Readings are normal")

        escalation, response = _escalation(tier)
        approvals = self._approvals(tier, prog.affected_component_id, inp.estimated_requisition_cost)
        return SafetyAssessment(
            risk_tier=tier,
            rationale=rationale,
            escalation=escalation,
            recommended_response=response,
            notify_technician=tier in (RiskTier.high, RiskTier.critical),
            required_approvals=approvals,
            safety_notices=SAFETY_NOTICES,
            policy_version=POLICY_VERSION,
        )

    def _approvals(self, tier: RiskTier, component: str | None, cost: float | None) -> list[ApprovalPolicy]:
        if tier == RiskTier.routine or component is None:
            return []
        req_roles = [ApproverRole.maintenance_supervisor]
        req_reason = "Purchase requisitions require maintenance supervisor approval."
        if cost is not None and cost > self.policy.operations_cost_threshold_usd:
            req_roles.append(ApproverRole.operations_manager)
            req_reason += f" Estimated cost above ${self.policy.operations_cost_threshold_usd:,.0f} also requires operations."
        wo_roles = [ApproverRole.maintenance_supervisor]
        wo_reason = "Dispatching physical work requires maintenance supervisor approval and an isolation attestation."
        if tier == RiskTier.critical:
            wo_roles.append(ApproverRole.operations_manager)
            wo_reason += " Critical tier: operations manager decides on production impact / controlled stop."
        return [
            ApprovalPolicy(action_kind=ActionKind.submit_requisition, roles=req_roles,
                           requires_isolation_attestation=False, reason=req_reason),
            ApprovalPolicy(action_kind=ActionKind.dispatch_work_order, roles=wo_roles,
                           requires_isolation_attestation=True, reason=wo_reason),
        ]


def _escalation(tier: RiskTier) -> tuple[list[str], str]:
    if tier == RiskTier.critical:
        return (
            ["SMS on-shift technician now", "Escalate to maintenance supervisor and operations manager"],
            "Operations to decide on a controlled stop. Technician to confirm on site.",
        )
    if tier == RiskTier.high:
        return (
            ["SMS on-shift technician", "Maintenance supervisor review within the current shift"],
            "Repair in the next planned downtime. Technician to confirm on site.",
        )
    if tier == RiskTier.elevated:
        return (
            ["Add to maintenance planning queue"],
            "Check on site at the next opportunity and keep monitoring.",
        )
    return ([], "No action needed.")
