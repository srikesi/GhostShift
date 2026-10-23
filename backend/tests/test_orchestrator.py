from __future__ import annotations

import time

from ghostshift.container import build_container
from ghostshift.integrations.base import ProviderError, ProviderNotConfigured
from ghostshift.schemas.agents import RiskTier
from ghostshift.schemas.common import StageStatus
from ghostshift.schemas.workflow import NotificationStatus, WorkflowStatus

from .conftest import CH, CRAH, VALID_NARRATIVE, FakeLLM, make_settings


def stage(run, name):
    return next(s for s in run.stages if s.name == name)


def run_at(container, machine_id, cursor):
    container.orchestrator.set_cursor(machine_id, cursor)
    return container.orchestrator.run(machine_id)


def test_normal_run_creates_no_incident(container):
    run = run_at(container, CRAH, 120)
    assert run.status == WorkflowStatus.completed_no_incident
    assert run.incident_id is None
    assert [s.name for s in run.stages] == ["telemetry", "diagnostics"]


def test_anomalous_run_full_pipeline(container):
    run = run_at(container, CRAH, 216)
    assert run.status == WorkflowStatus.awaiting_approval
    names = [s.name for s in run.stages]
    assert names == ["telemetry", "diagnostics", "prognostics", "safety_supervisor", "maintenance_supply",
                     "safety_gate", "narrative", "records", "autopilot", "notification"]
    assert stage(run, "autopilot").status == StageStatus.skipped  # off by default
    assert all(s.status == StageStatus.success for s in run.stages if s.name != "autopilot")
    inc = container.store.incidents[run.incident_id]
    assert inc.affected_component_id == "fan_bearing"
    assert inc.narrative_status == StageStatus.success and inc.narrative_provider.real is False
    assert len(inc.action_ids) == 2 and inc.requisition_id and inc.work_order_id
    note = container.store.notifications[inc.notification_ids[0]]
    assert note.status == NotificationStatus.simulated_sent
    assert "CRAH-07" in note.body and "HIGH" in note.body and "/m/" in note.body
    assert "+1512555" not in note.to_masked  # masked


def test_runs_are_deterministic(container):
    a = run_at(container, CH, 150)
    other = build_container(make_settings())
    b = run_at(other, CH, 150)
    ia, ib = container.store.incidents[a.incident_id], other.store.incidents[b.incident_id]
    assert ia.diagnostics == ib.diagnostics
    assert ia.prognostics.rul == ib.prognostics.rul
    assert ia.safety == ib.safety


def test_escalation_reuses_incident_and_renotifies(container):
    o = container.orchestrator
    o.set_cursor(CRAH, 170)
    _, first = o.monitor(CRAH)
    inc = container.store.incidents[first.incident_id]
    assert inc.safety.risk_tier == RiskTier.elevated
    assert stage(first, "notification").status == StageStatus.skipped
    o.set_cursor(CRAH, 216)
    _, second = o.monitor(CRAH)
    assert second.incident_id == first.incident_id
    o.set_cursor(CRAH, 239)
    _, third = o.monitor(CRAH)
    inc = container.store.incidents[first.incident_id]
    assert inc.safety.risk_tier == RiskTier.critical and len(inc.run_ids) == 3
    bodies = [container.store.notifications[n].body for n in inc.notification_ids]
    assert len(bodies) == 2 and "ESCALATED to CRITICAL" in bodies[1]
    # Pending work-order action gained the operations approval required at critical tier.
    wo_action = next(container.store.actions[a] for a in inc.action_ids
                     if container.store.actions[a].kind.value == "dispatch_work_order")
    assert {a.role.value for a in wo_action.approvals} == {"maintenance_supervisor", "operations_manager"}
    # No re-run while nothing escalates.
    _, none = o.monitor(CRAH)
    assert none is None


def _llm_container(mode, llm):
    return build_container(make_settings(mode=mode, llm_max_attempts=2), llm=llm)


def test_llm_success_is_labelled_real():
    c = _llm_container("aws", FakeLLM(VALID_NARRATIVE))
    run = run_at(c, CRAH, 216)
    rec = stage(run, "narrative")
    assert rec.status == StageStatus.success and rec.provider.real and rec.attempts == 1
    assert c.store.incidents[run.incident_id].narrative.headline == "CRAH-07 fan bearing wear detected"


def test_llm_failure_auto_mode_falls_back_and_says_so():
    llm = FakeLLM(ProviderError("Bedrock AccessDeniedException"))
    c = _llm_container("auto", llm)
    run = run_at(c, CRAH, 216)
    rec = stage(run, "narrative")
    assert rec.status == StageStatus.deterministic_fallback
    assert "AccessDenied" in rec.error and rec.fallback_reason
    assert llm.calls == 1  # non-retryable: no retry
    assert c.store.incidents[run.incident_id].narrative_status == StageStatus.deterministic_fallback
    assert run.status == WorkflowStatus.awaiting_approval  # workflow continues


def test_llm_failure_aws_mode_reports_provider_failure():
    c = _llm_container("aws", FakeLLM(ProviderNotConfigured("GHOSTSHIFT_BEDROCK_MODEL_ID is not set")))
    run = run_at(c, CRAH, 216)
    rec = stage(run, "narrative")
    assert rec.status == StageStatus.provider_failure
    inc = c.store.incidents[run.incident_id]
    assert inc.narrative_status == StageStatus.provider_failure and inc.narrative_provider.real is False


def test_retryable_llm_error_is_retried_with_bound():
    llm = FakeLLM(ProviderError("Throttling", retryable=True))
    c = _llm_container("auto", llm)
    rec = stage(run_at(c, CRAH, 216), "narrative")
    assert llm.calls == 2 and rec.status == StageStatus.deterministic_fallback


def test_invalid_llm_output_retries_then_falls_back():
    llm = FakeLLM("not json", '{"headline": "short"}')
    c = _llm_container("auto", llm)
    rec = stage(run_at(c, CRAH, 216), "narrative")
    assert llm.calls == 2 and rec.status == StageStatus.deterministic_fallback
    c2 = _llm_container("aws", FakeLLM("not json"))
    assert stage(run_at(c2, CRAH, 216), "narrative").status == StageStatus.invalid_result


def test_invalid_then_valid_output_succeeds_on_retry():
    llm = FakeLLM("garbage", VALID_NARRATIVE)
    c = _llm_container("aws", llm)
    rec = stage(run_at(c, CRAH, 216), "narrative")
    assert rec.status == StageStatus.success and rec.attempts == 2


def test_llm_cannot_change_safety_outputs():
    sneaky = VALID_NARRATIVE[:-1] + ', "risk_tier": "routine"}'
    c = _llm_container("aws", FakeLLM(sneaky))
    run = run_at(c, CRAH, 216)
    inc = c.store.incidents[run.incident_id]
    assert stage(run, "narrative").status == StageStatus.invalid_result
    assert inc.safety.risk_tier == RiskTier.high


def test_llm_timeout_is_bounded():
    def slow():
        time.sleep(1.0)
        raise AssertionError("unreachable")

    c = build_container(make_settings(mode="auto", llm_timeout_s=0.1, llm_max_attempts=1), llm=FakeLLM(slow))
    rec = stage(run_at(c, CRAH, 216), "narrative")
    assert rec.status == StageStatus.deterministic_fallback and "Timed out" in rec.error


def test_deterministic_stage_failure_marks_run_failed(container, monkeypatch):
    def boom(_):
        raise RuntimeError("bad fixture")

    monkeypatch.setattr(container.orchestrator.prognostics, "run", boom)
    run = run_at(container, CRAH, 216)
    assert run.status == WorkflowStatus.failed
    assert stage(run, "prognostics").status == StageStatus.provider_failure
    assert "bad fixture" in run.error and run.incident_id is None


def test_maintenance_failure_does_not_block_notification(container, monkeypatch):
    monkeypatch.setattr(container.orchestrator.maintenance, "run", lambda _: (_ for _ in ()).throw(RuntimeError("catalog down")))
    run = run_at(container, CRAH, 216)
    assert stage(run, "maintenance_supply").status == StageStatus.provider_failure
    assert stage(run, "notification").status == StageStatus.success
    inc = container.store.incidents[run.incident_id]
    assert inc.maintenance is None and inc.action_ids == []
