"""Each agent is tested directly, without an LLM or the API."""

from __future__ import annotations

import pytest

from ghostshift.agents import narrative as narr
from ghostshift.schemas.agents import (
    ActionKind,
    ApproverRole,
    DiagnosticsInput,
    MaintenanceInput,
    PrognosticsInput,
    RiskTier,
    SafetyInput,
)
from ghostshift.schemas.common import DataSource, Severity

from .conftest import CMP, VMC


def analyse(container, machine_id, cursor):
    o = container.orchestrator
    ref = container.reference
    sc = ref.scenarios[machine_id]
    m = ref.machine(machine_id)
    w = o.window(machine_id, cursor)
    d = o.diagnostics.run(DiagnosticsInput(machine=m, window=w, baseline_start_index=sc.baseline_start_index,
                                           baseline_end_index=sc.baseline_end_index))
    p = o.prognostics.run(PrognosticsInput(machine=m, window=w, diagnostics=d, as_of=w.points[-1].timestamp))
    s = o.safety.run(SafetyInput(diagnostics=d, prognostics=p))
    return m, w, d, p, s


@pytest.mark.parametrize("machine_id", [VMC, CMP])
def test_normal_window_has_no_anomalies(container, machine_id):
    _, _, d, p, s = analyse(container, machine_id, container.reference.scenarios[machine_id].initial_cursor)
    assert d.severity == Severity.normal
    assert d.anomalies == [] and d.hypotheses == []
    assert p.rul is None
    assert s.risk_tier == RiskTier.routine
    assert s.required_approvals == []


def test_spindle_bearing_scenario(container):
    _, _, d, p, s = analyse(container, VMC, 216)
    assert d.severity == Severity.warning
    assert d.hypotheses[0].fault_mode_id == "FM-VMC-SPB-WEAR"
    assert d.hypotheses[0].component_id == "spindle_front_bearing"
    vib = next(a for a in d.sensors if a.sensor_id == "spindle_vib_rms")
    assert vib.anomalous and vib.z_score > 3 and vib.limit_state.value == "alert"
    assert d.anomalies[0].evidence_id in {e.id for e in d.evidence}
    assert d.provenance.upstream_source == DataSource.simulated
    assert p.affected_component_id == "spindle_front_bearing"
    assert s.risk_tier == RiskTier.high
    assert s.notify_technician


def test_thermal_scenario_identifies_oil_cooler(container):
    _, _, d, p, _ = analyse(container, CMP, 150)
    assert d.hypotheses[0].fault_mode_id == "FM-CMP-COOLER-FOUL"
    assert p.affected_component_id == "oil_cooler"
    # The fan-failure signature must not match: fan current is stable.
    assert "FM-CMP-FAN-FAIL" not in {h.fault_mode_id for h in d.hypotheses}


def test_context_sensor_never_raises_severity(container):
    _, _, d, _, _ = analyse(container, VMC, 216)
    speed = next(a for a in d.sensors if a.sensor_id == "spindle_speed")
    assert speed.role == "context" and speed.severity == Severity.normal


def test_rul_is_qualified_and_separate_from_risk(container):
    _, _, _, p, _ = analyse(container, VMC, 216)
    rul, risk = p.rul, p.failure_risk
    assert rul.supportable and rul.unit == "hours"
    assert rul.lower_hours <= rul.value_hours <= rul.upper_hours
    assert "trend_extrapolation" in rul.method and rul.threshold == 7.1
    assert rul.provenance.upstream_source == DataSource.simulated
    assert risk.calibrated is False and "not a probability" in risk.definition
    assert any("simulated" in lim for lim in p.limitations)


def test_rul_not_supportable_without_deviation(container):
    _, _, _, p, _ = analyse(container, VMC, 216)
    motor = next(h for h in p.component_health if h.component_id == "coolant_pump")
    assert motor.rul is not None and motor.rul.supportable is False and motor.rul.value_hours is None
    assert motor.remaining_service_interval.method == "maintenance_interval"


def test_uninstrumented_components_report_interval_only(container):
    _, _, _, p, _ = analyse(container, VMC, 216)
    tc = next(h for h in p.component_health if h.component_id == "tool_changer")
    assert tc.basis.value == "interval_only" and tc.health_score is None and tc.rul is None


def test_safety_escalates_to_critical_near_end(container):
    _, _, _, p, s = analyse(container, VMC, 239)
    assert s.risk_tier == RiskTier.critical
    wo = next(a for a in s.required_approvals if a.action_kind == ActionKind.dispatch_work_order)
    assert ApproverRole.operations_manager in wo.roles and wo.requires_isolation_attestation
    assert any("do not stop, isolate" in n for n in s.safety_notices)


def test_safety_cost_threshold_adds_operations_approval(container):
    _, _, d, p, _ = analyse(container, VMC, 216)
    s = container.orchestrator.safety.run(SafetyInput(diagnostics=d, prognostics=p, estimated_requisition_cost=9650))
    req = next(a for a in s.required_approvals if a.action_kind == ActionKind.submit_requisition)
    assert ApproverRole.operations_manager in req.roles


def test_maintenance_proposal(container):
    m, w, d, p, s = analyse(container, VMC, 216)
    mp = container.orchestrator.maintenance.run(
        MaintenanceInput(machine=m, diagnostics=d, prognostics=p, safety=s, as_of=w.points[-1].timestamp))
    assert mp.proposed_part.sku == "FZ-BRG-7014-P4DB"
    assert mp.proposed_part.availability.provenance.source == DataSource.simulated
    assert mp.proposed_part.cost_provenance.source == DataSource.fixture
    assert mp.maintenance_window is not None and mp.maintenance_window.before_rul_lower_bound is True
    assert mp.work_order.priority.startswith("P2")
    assert any(t.requires_qualified_person for t in mp.work_order.tasks)


def test_maintenance_flags_window_after_rul(container):
    m, w, d, p, s = analyse(container, CMP, 205)
    mp = container.orchestrator.maintenance.run(
        MaintenanceInput(machine=m, diagnostics=d, prognostics=p, safety=s, as_of=w.points[-1].timestamp))
    assert mp.proposed_part.sku == "FZ-OCL-CLN-KIT"  # in stock beats the 3-day-lead core
    assert mp.maintenance_window.before_rul_lower_bound is False
    assert any("Operations needs to decide" in x for x in mp.warnings)


def test_narrative_parser_validates_and_rejects_unsafe_claims():
    ok = narr.parse('Here you go: {"headline": "Bearing wear on VMC-07", "summary": "Vibration up and crossing alert.",'
                    ' "technician_brief": "Inspect the spindle bearing.", "sms_key_finding": "vibration up"}')
    assert ok.headline.startswith("Bearing")
    with pytest.raises(narr.InvalidNarrative):
        narr.parse("no json here")
    with pytest.raises(narr.InvalidNarrative):
        narr.parse('{"headline": "x"}')
    with pytest.raises(narr.InvalidNarrative):
        narr.parse('{"headline": "Bearing wear on VMC-07", "summary": "The machine has been isolated and is fine.",'
                   ' "technician_brief": "It is safe to service now.", "sms_key_finding": "all good"}')
    with pytest.raises(narr.InvalidNarrative):  # extra fields such as a tier override are rejected
        narr.parse('{"headline": "Bearing wear on VMC-07", "summary": "Vibration up and crossing alert.",'
                   ' "technician_brief": "Inspect the spindle bearing.", "sms_key_finding": "vibration up",'
                   ' "risk_tier": "routine"}')
