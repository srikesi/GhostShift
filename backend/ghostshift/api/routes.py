"""REST API. Thin: validates input, calls the orchestrator/services, shapes output."""

from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from starlette.responses import StreamingResponse

from .. import APP_NAME, __version__
from ..container import Container
from ..integrations.base import ProviderHealth
from ..schemas.agents import PrognosticsInput
from ..schemas.common import Contract, DataSource, Provenance, ProviderInfo, Severity, StageStatus
from ..schemas.machine import ComponentHealth, Machine, MachineSummary
from ..schemas.telemetry import FaultInjectRequest, ReplayRequest, ReplayResponse, ScenarioPhase, TelemetryResponse
from ..schemas.agents import DiagnosticsResult
from ..schemas.workflow import (
    ActionStatus,
    BriefingResponse,
    ComponentWithHealth,
    DecisionRequest,
    IncidentView,
    InspectionView,
    Notification,
    NotificationStatus,
    ProposedAction,
    Requisition,
    WorkflowRun,
    WorkOrder,
)

router = APIRouter(prefix="/api")


def get_container(request: Request) -> Container:
    return request.app.state.container


def _machine_or_404(c: Container, machine_id: str) -> Machine:
    if machine_id not in c.reference.machines:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Machine '{machine_id}' not found")
    return c.reference.machine(machine_id)


# ---------------------------------------------------------------- health
class HealthResponse(Contract):
    status: str
    app: str
    version: str
    mode: str
    providers: list[ProviderHealth]
    simulated_capabilities: list[str]


@router.get("/health", response_model=HealthResponse)
def health(probe: bool = False, c: Container = Depends(get_container)) -> HealthResponse:
    providers = c.provider_health(probe=probe)
    return HealthResponse(
        status="ok", app=APP_NAME, version=__version__, mode=c.settings.mode.value, providers=providers,
        simulated_capabilities=sorted({p.capability for p in providers if not p.provider.real}),
    )


# -------------------------------------------------------------- machines
class MachineDetail(Contract):
    machine: Machine
    summary: MachineSummary
    screening: DiagnosticsResult
    component_health: list[ComponentHealth]


def _summary(c: Container, machine: Machine) -> MachineSummary:
    o = c.orchestrator
    cursor = o.cursor(machine.id)
    s = o.screen(machine.id)
    inc = c.store.open_incident_for(machine.id)
    sev, note = s.diagnostics.severity, _screen_note(s.diagnostics)
    if inc and inc.severity.rank > sev.rank:
        sev, note = inc.severity, f"Open incident {inc.id}; latest screening: {note}"
    return MachineSummary(
        id=machine.id, display_name=machine.display_name, machine_type=machine.machine_type, model=machine.model,
        site=machine.context.site, line=machine.context.line, status=sev, status_note=note,
        open_incident_id=inc.id if inc else None, open_incident_tier=inc.safety.risk_tier.value if inc else None,
        replay_cursor=cursor, replay_length=o.telemetry.length(machine.id),
    )


def _screen_note(d: DiagnosticsResult) -> str:
    if not d.anomalies:
        return "All monitored signals within baseline"
    a = d.anomalies[0]
    return a.description.split(";")[0]


@router.get("/machines", response_model=list[MachineSummary])
def list_machines(c: Container = Depends(get_container)):
    return [_summary(c, c.reference.machine(mid)) for mid in c.telemetry.machine_ids()]


@router.get("/machines/{machine_id}", response_model=MachineDetail)
def get_machine(machine_id: str, c: Container = Depends(get_container)):
    m = _machine_or_404(c, machine_id)
    o = c.orchestrator
    s = o.screen(machine_id)
    window = o.window(machine_id)
    prog = o.prognostics.run(PrognosticsInput(machine=m, window=window, diagnostics=s.diagnostics,
                                              as_of=window.points[-1].timestamp))
    inc = c.store.open_incident_for(machine_id)
    health = inc.prognostics.component_health if inc and inc.prognostics.machine_id == machine_id else prog.component_health
    # Prefer the live screening when it is at least as severe as the incident snapshot.
    if not inc or s.diagnostics.severity.rank >= inc.severity.rank:
        health = prog.component_health
    return MachineDetail(machine=m, summary=_summary(c, m), screening=s.diagnostics, component_health=health)


@router.get("/machines/{machine_id}/telemetry", response_model=TelemetryResponse)
def get_telemetry(machine_id: str, c: Container = Depends(get_container)):
    _machine_or_404(c, machine_id)
    o = c.orchestrator
    sc = c.reference.scenarios[machine_id]
    cursor = o.cursor(machine_id)
    window = o.window(machine_id)
    label_prov = Provenance(source=DataSource.simulated, detail="Scenario ground-truth label (not used by diagnostics)")
    return TelemetryResponse(
        machine_id=machine_id, cursor=cursor, length=o.telemetry.length(machine_id),
        baseline_start_index=sc.baseline_start_index, baseline_end_index=sc.baseline_end_index, window=window,
        scenario_phases=[ScenarioPhase(label=p.label, start_index=p.start_index, end_index=p.end_index,
                                       provenance=label_prov) for p in sc.phases],
        detection_segments=o.severity_segments(machine_id, cursor),
    )


@router.post("/machines/{machine_id}/replay", response_model=ReplayResponse)
def replay(machine_id: str, body: ReplayRequest, c: Container = Depends(get_container)):
    _machine_or_404(c, machine_id)
    o = c.orchestrator
    sc = c.reference.scenarios[machine_id]
    if body.action == "reset":
        cursor = o.set_cursor(machine_id, sc.initial_cursor)
        with c.store.lock:
            for inc in c.store.incidents.values():
                if inc.machine_id == machine_id and inc.status == "open":
                    inc.status = "closed"
    elif body.action == "advance":
        cursor = o.set_cursor(machine_id, o.cursor(machine_id) + body.steps)
    elif body.action == "to_end":
        cursor = o.set_cursor(machine_id, o.telemetry.length(machine_id) - 1)
    else:
        cursor = o.set_cursor(machine_id, body.cursor if body.cursor is not None else sc.jump_cursor)

    run = None
    if body.auto_analyze and body.action != "reset":
        screening, run = o.monitor(machine_id)
    else:
        screening = o.screen(machine_id)
    return ReplayResponse(
        machine_id=machine_id, cursor=cursor, length=o.telemetry.length(machine_id),
        screening_severity=screening.diagnostics.severity, screening_note=_screen_note(screening.diagnostics),
        triggered_run_id=run.id if run else None, triggered_incident_id=run.incident_id if run else None,
    )


@router.post("/machines/{machine_id}/workflow", response_model=WorkflowRun, status_code=201)
def run_workflow(machine_id: str, c: Container = Depends(get_container)):
    _machine_or_404(c, machine_id)
    return c.orchestrator.run(machine_id, trigger="manual")


@router.get("/workflows", response_model=list[WorkflowRun])
def list_runs(machine_id: str | None = None, c: Container = Depends(get_container)):
    runs = [r for r in c.store.runs.values() if machine_id is None or r.machine_id == machine_id]
    return sorted(runs, key=lambda r: r.created_at, reverse=True)


@router.get("/workflows/{run_id}", response_model=WorkflowRun)
def get_run(run_id: str, c: Container = Depends(get_container)):
    run = c.store.runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"Workflow run '{run_id}' not found")
    return run


# ------------------------------------------------------------- incidents
def _view(c: Container, incident_id: str) -> IncidentView:
    st = c.store
    inc = st.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(404, f"Incident '{incident_id}' not found")
    return IncidentView(
        incident=inc,
        actions=[st.actions[a] for a in inc.action_ids],
        requisition=st.requisitions.get(inc.requisition_id) if inc.requisition_id else None,
        work_order=st.work_orders.get(inc.work_order_id) if inc.work_order_id else None,
        notifications=[st.notifications[n] for n in inc.notification_ids],
        latest_run=st.runs.get(inc.run_ids[-1]) if inc.run_ids else None,
        activity=st.activity_for(inc.id),
    )


@router.get("/incidents", response_model=list[IncidentView])
def list_incidents(machine_id: str | None = None, status_: str | None = Query(None, alias="status"),
                   c: Container = Depends(get_container)):
    ids = [i.id for i in sorted(c.store.incidents.values(), key=lambda i: i.created_at, reverse=True)
           if (machine_id is None or i.machine_id == machine_id) and (status_ is None or i.status == status_)]
    return [_view(c, i) for i in ids]


@router.get("/incidents/{incident_id}", response_model=IncidentView)
def get_incident(incident_id: str, c: Container = Depends(get_container)):
    return _view(c, incident_id)


_audio_cache: dict[tuple[str, str], tuple[bytes, str]] = {}


def _briefing(c: Container, incident_id: str, audio_base: str) -> BriefingResponse:
    inc = c.store.incidents.get(incident_id)
    if inc is None:
        raise HTTPException(404, f"Incident '{incident_id}' not found")
    text = f"{inc.narrative.headline}. {inc.narrative.technician_brief} {inc.safety.recommended_response}"
    key = (inc.id, inc.updated_at.isoformat())
    error, status_ = None, StageStatus.success
    if key not in _audio_cache:
        result = c.voice.synthesize(text)
        if result.audio:
            _audio_cache[key] = (result.audio, result.mime_type or "audio/mpeg")
        elif result.error:
            error, status_ = result.error, StageStatus.provider_failure
    has_audio = key in _audio_cache
    return BriefingResponse(incident_id=inc.id, text=text, audio_available=has_audio,
                            audio_url=f"{audio_base}/audio" if has_audio else None, provider=c.voice.info,
                            status=status_, error=error)


def _audio(c: Container, incident_id: str) -> Response:
    inc = c.store.incidents.get(incident_id)
    hit = _audio_cache.get((inc.id, inc.updated_at.isoformat())) if inc else None
    if hit is None:
        raise HTTPException(404, "No audio available for this briefing")
    return Response(content=hit[0], media_type=hit[1])


@router.get("/incidents/{incident_id}/briefing", response_model=BriefingResponse)
def incident_briefing(incident_id: str, c: Container = Depends(get_container)):
    return _briefing(c, incident_id, f"/api/incidents/{incident_id}/briefing")


@router.get("/incidents/{incident_id}/briefing/audio")
def incident_briefing_audio(incident_id: str, c: Container = Depends(get_container)):
    return _audio(c, incident_id)


# --------------------------------------------------- records & approvals
@router.get("/work-orders", response_model=list[WorkOrder])
def list_work_orders(c: Container = Depends(get_container)):
    return list(c.store.work_orders.values())


@router.get("/work-orders/{wo_id}", response_model=WorkOrder)
def get_work_order(wo_id: str, c: Container = Depends(get_container)):
    wo = c.store.work_orders.get(wo_id)
    if wo is None:
        raise HTTPException(404, f"Work order '{wo_id}' not found")
    return wo


@router.get("/requisitions", response_model=list[Requisition])
def list_requisitions(c: Container = Depends(get_container)):
    return list(c.store.requisitions.values())


@router.get("/approvals", response_model=list[ProposedAction])
def list_approvals(status_: ActionStatus | None = Query(None, alias="status"), c: Container = Depends(get_container)):
    return [a for a in c.store.actions.values() if status_ is None or a.status == status_]


@router.post("/actions/{action_id}/decision", response_model=ProposedAction)
def decide(action_id: str, body: DecisionRequest, c: Container = Depends(get_container)):
    return c.approvals.decide(action_id, body)


@router.post("/actions/{action_id}/execute", response_model=ProposedAction)
def execute(action_id: str, c: Container = Depends(get_container)):
    return c.approvals.execute(action_id)


@router.post("/notifications/{notification_id}/check", response_model=Notification)
def check_notification(notification_id: str, c: Container = Depends(get_container)):
    """Ask the provider whether an accepted text was actually delivered, and record the answer."""
    n = c.store.notifications.get(notification_id)
    if n is None:
        raise HTTPException(404, f"Notification '{notification_id}' not found")
    check = getattr(c.orchestrator.sms, "delivery_status", None)
    if n.status != NotificationStatus.sent or not n.external_id or check is None:
        return n
    d = check(n.external_id)
    with c.store.lock:
        if d.state == "delivered":
            n.status, n.error = NotificationStatus.delivered, None
        elif d.state == "failed":
            n.status, n.error = NotificationStatus.failed, d.error
            c.store.notified_tier.pop(n.incident_id, None)  # let a later run try again
            c.store.log(n.incident_id, "ghostshift", "GhostShift", "notify_failed",
                        f"Text to {n.recipient_label.split(' · ')[0]} was not delivered: {d.error}",
                        c.orchestrator.machine_time(n.incident_id))
    return n


@router.get("/notifications", response_model=list[Notification])
def list_notifications(incident_id: str | None = None, c: Container = Depends(get_container)):
    return [n for n in c.store.notifications.values() if incident_id is None or n.incident_id == incident_id]


# ------------------------------------------------------ mobile inspection
def _grant_or_404(c: Container, token: str):
    grant = c.store.resolve_grant(token)
    if grant is None:
        # Same response for unknown and expired tokens; no detail leaks.
        raise HTTPException(404, "Inspection link is invalid or has expired")
    return grant


@router.get("/inspect/{token}", response_model=InspectionView)
def inspect(token: str, c: Container = Depends(get_container)):
    grant = _grant_or_404(c, token)
    inc = c.store.incidents[grant.incident_id]
    m = c.reference.machine(inc.machine_id)
    health = {h.component_id: h for h in inc.prognostics.component_health}
    wo = c.store.work_orders.get(inc.work_order_id) if inc.work_order_id else None
    return InspectionView(
        incident=inc, machine_name=m.display_name, machine_id=m.id, drawing=m.drawing,
        components=[ComponentWithHealth(component=comp, health=health.get(comp.id)) for comp in m.components],
        work_order=wo, expires_at=grant.expires_at,
    )


@router.get("/inspect/{token}/briefing", response_model=BriefingResponse)
def inspect_briefing(token: str, c: Container = Depends(get_container)):
    grant = _grant_or_404(c, token)
    return _briefing(c, grant.incident_id, f"/api/inspect/{token}/briefing")


@router.get("/inspect/{token}/briefing/audio")
def inspect_briefing_audio(token: str, c: Container = Depends(get_container)):
    grant = _grant_or_404(c, token)
    return _audio(c, grant.incident_id)


# ------------------------------------------------------------------ demo
@router.post("/demo/reset", status_code=204)
def demo_reset(c: Container = Depends(get_container)):
    c.reset()
    _audio_cache.clear()
    return Response(status_code=204)



# ------------------------------------------------------------- streaming
@router.get("/machines/{machine_id}/stream")
async def stream_machine_telemetry(
    machine_id: str,
    request: Request,
    speed: float = Query(default=1.0, ge=0.1, le=100.0, description="Playback speed multiplier"),
    loop: bool = Query(default=True, description="Whether to loop the stream when reaching the end"),
    c: Container = Depends(get_container),
):
    _machine_or_404(c, machine_id)
    o = c.orchestrator
    total_len = o.telemetry.length(machine_id)

    async def event_generator():
        cursor = o.cursor(machine_id)
        while True:
            if await request.is_disconnected():
                break
            tick = o.telemetry.stream_tick(machine_id, cursor)
            payload = tick.model_dump(mode="json") if hasattr(tick, "model_dump") else (tick.dict() if hasattr(tick, "dict") else tick)
            yield f"event: telemetry\ndata: {json.dumps(payload)}\n\n"

            cursor += 1
            if cursor >= total_len:
                if loop:
                    cursor = 0
                else:
                    yield 'event: end\ndata: {"status": "stream_complete"}\n\n'
                    break
            await asyncio.sleep(0.001 if speed >= 50.0 else (1.0 / speed))

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/telemetry/stream")
async def stream_telemetry_default(
    request: Request,
    machine_id: str = Query(default="VMC-07-MULTIMODAL"),
    speed: float = Query(default=1.0, ge=0.1, le=100.0),
    loop: bool = Query(default=True),
    c: Container = Depends(get_container),
):
    return await stream_machine_telemetry(machine_id, request, speed=speed, loop=loop, c=c)



def _demo_call(c: Container, machine_id: str) -> dict | None:
    """Breakdown and emergency stop: phone the scheduler contact straight away to agree a repair date."""
    inc = c.store.open_incident_for(machine_id)
    if inc is None:
        return None
    try:
        call = c.calls.start(inc.id)
    except Exception:  # noqa: BLE001 - no slot, no phone number or a failed dial must not break the trigger
        return None
    return {"id": call.id, "status": call.status, "error": call.error}


def _demo_link(c: Container, machine_id: str, cursor_offset: int) -> str:
    """Open (or update) a real incident for a demo trigger and return a working technician link.

    The phone page needs a token tied to an incident, so a bare /m/<machine id> never opened. If no
    incident can be made, fall back to the machine's dashboard page.
    """
    o = c.orchestrator
    sc = c.reference.scenarios.get(machine_id)
    if sc is not None:
        o.set_cursor(machine_id, max(o.cursor(machine_id), sc.jump_cursor + cursor_offset))
        o.monitor(machine_id)
    inc = c.store.open_incident_for(machine_id)
    base = c.settings.public_base_url
    if inc is None:
        return f"{base}/machines/{machine_id}"
    token, _ = c.store.issue_grant(inc.id, c.settings.inspection_token_ttl_hours)
    return f"{base}/m/{token}"


@router.post("/machines/{machine_id}/inject-fault")
async def inject_fault(
    machine_id: str,
    body: FaultInjectRequest,
    request: Request,
    c: Container = Depends(get_container),
):
    _machine_or_404(c, machine_id)
    adapter = c.telemetry._for(machine_id)
    if hasattr(adapter, "inject_fault"):
        adapter.inject_fault(machine_id, body.fault_type)
    elif hasattr(c.telemetry, "inject_fault"):
        c.telemetry.inject_fault(machine_id, body.fault_type)

    link = _demo_link(c, machine_id, -44 if body.fault_type == "mild" else 0)
    # Differentiated Twilio Notification dispatch
    if body.fault_type == "mild":
        sms_text = (
            f"⚠️ WARNING {machine_id}: Incipient fan bearing flutter detected (2.95 mm/s, 82dB). "
            f"Status: WATCH. Open: {link} | Human decision required."
        )
    else:
        sms_text = (
            f"🚨 CRITICAL {machine_id}: Catastrophic shaft collapse & thermal runaway (89.2°C). "
            f"Autonomous E-STOP triggered: Power cut to 0A, Fan 0 RPM. Mandatory LOTO required before approach. Open: {link}"
        )
    
    if c.settings.demo_technician_phone:
        c.sms.send(to=c.settings.demo_technician_phone, body=sms_text)

    return {
        "status": "fault_injected",
        "machine_id": machine_id,
        "fault_type": body.fault_type,
        "sms_sent": sms_text,
        "call": _demo_call(c, machine_id) if body.fault_type == "critical" else None,
    }


@router.post("/machines/{machine_id}/emergency-stop")
async def emergency_stop(
    machine_id: str,
    request: Request,
    c: Container = Depends(get_container),
):
    _machine_or_404(c, machine_id)
    adapter = c.telemetry._for(machine_id)
    if hasattr(adapter, "emergency_stop"):
        adapter.emergency_stop(machine_id)
    elif hasattr(c.telemetry, "emergency_stop"):
        c.telemetry.emergency_stop(machine_id)

    link = _demo_link(c, machine_id, 0)
    sms_text = (
        f"🚨 EMERGENCY SHUTDOWN EXECUTED on {machine_id}: Equipment tripped offline. "
        f"Power cut: 0A, RPM: 0. Certified Lockout/Tagout (LOTO) sign-off mandatory before restart. Open: {link}"
    )
    if c.settings.demo_technician_phone:
        c.sms.send(to=c.settings.demo_technician_phone, body=sms_text)

    return {
        "status": "estop_active",
        "machine_id": machine_id,
        "current_a": 0.0,
        "rpm": 0.0,
        "sms_sent": sms_text,
        "call": _demo_call(c, machine_id),
    }


@router.post("/machines/{machine_id}/reset-fault")
async def reset_fault(
    machine_id: str,
    request: Request,
    c: Container = Depends(get_container),
):
    _machine_or_404(c, machine_id)
    adapter = c.telemetry._for(machine_id)
    if hasattr(adapter, "reset_fault"):
        adapter.reset_fault(machine_id)
    elif hasattr(c.telemetry, "reset_fault"):
        c.telemetry.reset_fault(machine_id)

    return {"status": "nominal_restored", "machine_id": machine_id}
