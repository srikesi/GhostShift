"""Workflow orchestrator.

Owns execution order, per-stage timeouts, exception handling, workflow status
and aggregation of agent results into incidents, records and notifications.

Stage order:
  telemetry → diagnostics → prognostics → safety_supervisor → maintenance_supply
  → safety_gate (re-check with proposal cost) → narrative → records → notification
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

from pydantic import ValidationError

from .agents import DiagnosticsAgent, MaintenanceSupplyAgent, PrognosticsAgent, SafetySupervisor
from .agents import narrative as narr
from .config import ExecutionMode, LlmProviderChoice, Settings
from .integrations.base import LlmProvider, ProviderError, SmsProvider, info
from .reference import ReferenceData
from .schemas.agents import (
    ActionKind,
    ApproverRole,
    DiagnosticsInput,
    DiagnosticsResult,
    IncidentNarrative,
    MaintenanceInput,
    MaintenanceProposal,
    NarrativeInput,
    PrognosticsInput,
    PrognosticsResult,
    RiskTier,
    SafetyAssessment,
    SafetyInput,
)
from .schemas.common import ProviderInfo, ProviderKind, Severity, StageStatus, utcnow
from .schemas.telemetry import SeveritySegment, TelemetryWindow
from .schemas.workflow import (
    ActionStatus,
    ApprovalRecord,
    AutonomyLevel,
    DecisionRequest,
    Decision,
    Incident,
    Notification,
    NotificationStatus,
    ProposedAction,
    RecordStatus,
    Requisition,
    StageRecord,
    WorkflowRun,
    WorkflowStatus,
    WorkOrder,
)
from .state import Store

TEMPLATE_PROVIDER = info("narrative-template", ProviderKind.deterministic)
DETERMINISTIC = info("ghostshift-deterministic", ProviderKind.deterministic)
TIER_RANK = {RiskTier.routine: 0, RiskTier.elevated: 1, RiskTier.high: 2, RiskTier.critical: 3}
PRIORITY = {RiskTier.routine: "Low", RiskTier.elevated: "Medium", RiskTier.high: "High", RiskTier.critical: "Urgent"}
AUTO_ORDER_NAME = "Auto-order policy"


class StageFailed(Exception):
    def __init__(self, record: StageRecord):
        super().__init__(record.error)
        self.record = record


@dataclass
class Screening:
    diagnostics: DiagnosticsResult
    tier: RiskTier | None


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        reference: ReferenceData,
        telemetry,
        store: Store,
        diagnostics: DiagnosticsAgent,
        prognostics: PrognosticsAgent,
        safety: SafetySupervisor,
        maintenance: MaintenanceSupplyAgent,
        llm: LlmProvider | None,
        sms: SmsProvider,
    ):
        self.settings = settings
        self.ref = reference
        self.telemetry = telemetry
        self.store = store
        self.diagnostics = diagnostics
        self.prognostics = prognostics
        self.safety = safety
        self.maintenance = maintenance
        self.llm = llm
        self.sms = sms
        self.approvals = None  # ApprovalService; set by the container (it needs this orchestrator's clock)
        self.calendar = None  # CalendarService, InventoryService and SchedulerCalls are also set by the container
        self.calls = None
        self.inventory = None
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ghostshift-stage")
        self._screen_cached = lru_cache(maxsize=4096)(self._screen_uncached)

    # ------------------------------------------------------------------ replay
    def cursor(self, machine_id: str) -> int:
        with self.store.lock:
            if machine_id not in self.store.cursors:
                self.store.cursors[machine_id] = self.ref.scenarios[machine_id].initial_cursor
            return self.store.cursors[machine_id]

    def set_cursor(self, machine_id: str, cursor: int) -> int:
        length = self.telemetry.length(machine_id)
        base_end = self.ref.scenarios[machine_id].baseline_end_index
        c = max(base_end + 1, min(length - 1, cursor))
        with self.store.lock:
            self.store.cursors[machine_id] = c
        return c

    def window(self, machine_id: str, cursor: int | None = None) -> TelemetryWindow:
        c = self.cursor(machine_id) if cursor is None else cursor
        return self.telemetry.window(machine_id, 0, c)

    def _diag_input(self, machine_id: str, window: TelemetryWindow) -> DiagnosticsInput:
        sc = self.ref.scenarios[machine_id]
        return DiagnosticsInput(machine=self.ref.machine(machine_id), window=window,
                                baseline_start_index=sc.baseline_start_index, baseline_end_index=sc.baseline_end_index)

    def _screen_uncached(self, machine_id: str, cursor: int) -> Screening:
        window = self.window(machine_id, cursor)
        diag = self.diagnostics.run(self._diag_input(machine_id, window))
        tier = None
        if diag.severity != Severity.normal:
            prog = self.prognostics.run(PrognosticsInput(machine=self.ref.machine(machine_id), window=window,
                                                         diagnostics=diag, as_of=window.points[-1].timestamp))
            tier = self.safety.run(SafetyInput(diagnostics=diag, prognostics=prog)).risk_tier
        return Screening(diag, tier)

    def screen(self, machine_id: str, cursor: int | None = None) -> Screening:
        """Cheap deterministic screening (no records, no notifications)."""
        return self._screen_cached(machine_id, self.cursor(machine_id) if cursor is None else cursor)

    def severity_segments(self, machine_id: str, upto: int) -> list[SeveritySegment]:
        start = self.ref.scenarios[machine_id].baseline_end_index + 1
        segs: list[SeveritySegment] = []
        for c in range(start, upto + 1):
            sev = self.screen(machine_id, c).diagnostics.severity
            if segs and segs[-1].severity == sev and segs[-1].end_index == c - 1:
                segs[-1].end_index = c
            else:
                segs.append(SeveritySegment(start_index=c, end_index=c, severity=sev))
        return segs

    def monitor(self, machine_id: str) -> tuple[Screening, WorkflowRun | None]:
        """Called after each replay step: run the full workflow on new or escalating findings."""
        s = self.screen(machine_id)
        if self.inventory is not None:
            self.inventory.sync()  # parts orders move along as the replay clock advances
        if s.diagnostics.severity == Severity.normal:
            return s, None
        inc = self.store.open_incident_for(machine_id)
        if inc is None or (
            s.diagnostics.severity.rank > inc.severity.rank
            or (s.tier and TIER_RANK[s.tier] > TIER_RANK[inc.safety.risk_tier])
        ):
            return s, self.run(machine_id, trigger="replay_monitor")
        return s, None

    # ---------------------------------------------------------------- workflow
    def run(self, machine_id: str, trigger: str = "manual") -> WorkflowRun:
        machine = self.ref.machine(machine_id)
        cursor = self.cursor(machine_id)
        run = WorkflowRun(
            id=self.store.next_id("RUN"), machine_id=machine_id, trigger=trigger, mode=self.settings.mode.value,
            analyzed_start_index=0, analyzed_end_index=cursor, status=WorkflowStatus.completed, stages=[],
            incident_id=None, created_at=utcnow(), completed_at=None,
        )
        try:
            self._execute(run, machine)
        except StageFailed as exc:
            run.status = WorkflowStatus.failed
            run.error = f"Stage '{exc.record.name}' failed: {exc.record.error}"
        run.completed_at = utcnow()
        with self.store.lock:
            self.store.runs[run.id] = run
        return run

    def _execute(self, run: WorkflowRun, machine) -> None:
        mid = machine.id
        tel_info = getattr(self.telemetry, "provider_info", lambda _m: self.telemetry.info)(mid)
        window = self._required(run, "telemetry", tel_info, lambda: self.window(mid, run.analyzed_end_index))
        as_of = window.points[-1].timestamp
        diag: DiagnosticsResult = self._required(run, "diagnostics", DETERMINISTIC,
                                                 lambda: self.diagnostics.run(self._diag_input(mid, window)))
        if diag.severity == Severity.normal:
            run.status = WorkflowStatus.completed_no_incident
            return
        prog: PrognosticsResult = self._required(
            run, "prognostics", DETERMINISTIC,
            lambda: self.prognostics.run(PrognosticsInput(machine=machine, window=window, diagnostics=diag, as_of=as_of)))
        safety: SafetyAssessment = self._required(
            run, "safety_supervisor", DETERMINISTIC,
            lambda: self.safety.run(SafetyInput(diagnostics=diag, prognostics=prog)))

        maint: MaintenanceProposal | None = None
        if prog.affected_component_id and safety.risk_tier != RiskTier.routine:
            maint, rec = self._stage("maintenance_supply", self.maintenance_info, lambda: self.maintenance.run(
                MaintenanceInput(machine=machine, diagnostics=diag, prognostics=prog, safety=safety, as_of=as_of)))
            if maint is not None:
                rec.warnings = maint.warnings
            run.stages.append(rec)
        else:
            run.stages.append(self._skipped("maintenance_supply", "No affected component or routine tier"))

        cost = maint.estimated_cost_usd if maint else None
        safety = self._required(run, "safety_gate", DETERMINISTIC, lambda: self.safety.run(
            SafetyInput(diagnostics=diag, prognostics=prog, estimated_requisition_cost=cost)))

        n_input = narr.build_input(machine, diag, prog, safety, maint)
        narrative, n_status, n_provider = self._narrative(run, n_input)

        before = self.store.open_incident_for(mid)
        before = before.model_copy() if before else None
        incident = self._required(run, "records", DETERMINISTIC, lambda: self._persist(
            run, machine, diag, prog, safety, maint, narrative, n_status, n_provider))
        run.incident_id = incident.id
        self._log_progress(incident, before, machine, n_input, as_of)
        if self.calendar is not None:
            self.calendar.sync_incident(incident.id)  # tentative hold; confirmed only after approval

        started, t0 = utcnow(), time.perf_counter()
        notes = self._autopilot(incident, as_of)
        run.stages.append(StageRecord(
            name="autopilot", status=StageStatus.success if notes is not None else StageStatus.skipped,
            provider=DETERMINISTIC, started_at=started, duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            attempts=1 if notes is not None else 0, warnings=notes or [],
            fallback_reason=None if notes is not None else "Autopilot is off; people approve orders"))

        if self.calls is not None:
            self.calls.maybe_auto_call(incident.id)  # Autopilot only; one call per incident
        self._notify(run, machine, incident, n_input, as_of)
        with self.store.lock:
            pending = any(self.store.actions[a].status == ActionStatus.awaiting_approval for a in incident.action_ids)
        run.status = WorkflowStatus.awaiting_approval if pending else WorkflowStatus.completed

    @property
    def maintenance_info(self) -> ProviderInfo:
        return self.maintenance._catalog.info  # parts data source drives this stage's provenance

    # ------------------------------------------------------------------ stages
    def _stage(self, name: str, provider: ProviderInfo, fn: Callable[[], Any],
               timeout: float | None = None) -> tuple[Any, StageRecord]:
        started, t0 = utcnow(), time.perf_counter()
        timeout = timeout or self.settings.stage_timeout_s
        result, status, error = None, StageStatus.success, None
        future = self._pool.submit(fn)
        try:
            result = future.result(timeout=timeout)
        except FuturesTimeout:
            status, error = StageStatus.provider_failure, f"Timed out after {timeout:g}s"
        except ValidationError as exc:
            status, error = StageStatus.invalid_result, f"Output failed validation: {exc.errors()[:2]}"
        except Exception as exc:  # noqa: BLE001 - orchestrator boundary
            status, error = StageStatus.provider_failure, f"{type(exc).__name__}: {exc}"
        record = StageRecord(name=name, status=status, provider=provider, started_at=started,
                             duration_ms=round((time.perf_counter() - t0) * 1000, 2), error=error)
        return result, record

    def _required(self, run: WorkflowRun, name: str, provider: ProviderInfo, fn: Callable[[], Any]) -> Any:
        result, rec = self._stage(name, provider, fn)
        if name == "diagnostics" and result is not None:
            rec.warnings = list(result.warnings)
        run.stages.append(rec)
        if rec.status != StageStatus.success:
            raise StageFailed(rec)
        return result

    @staticmethod
    def _skipped(name: str, reason: str) -> StageRecord:
        return StageRecord(name=name, status=StageStatus.skipped, provider=DETERMINISTIC, started_at=utcnow(),
                           duration_ms=0.0, attempts=0, fallback_reason=reason)

    def _narrative(self, run: WorkflowRun, inp: NarrativeInput) -> tuple[IncidentNarrative, StageStatus, ProviderInfo]:
        """Deterministic text always exists; the LLM may reword it. Status records which one was used."""
        started, t0 = utcnow(), time.perf_counter()
        fallback = narr.deterministic(inp)
        mode = self.settings.mode

        def record(status, provider, attempts=0, error=None, reason=None):
            run.stages.append(StageRecord(
                name="narrative", status=status, provider=provider, started_at=started,
                duration_ms=round((time.perf_counter() - t0) * 1000, 2), attempts=attempts, error=error,
                fallback_reason=reason))

        if self.llm is None:
            if mode == ExecutionMode.auto and self.settings.llm_provider == LlmProviderChoice.bedrock:
                record(StageStatus.deterministic_fallback, TEMPLATE_PROVIDER,
                       reason="Bedrock not configured (GHOSTSHIFT_BEDROCK_MODEL_ID unset)")
                return fallback, StageStatus.deterministic_fallback, TEMPLATE_PROVIDER
            record(StageStatus.success, TEMPLATE_PROVIDER)
            return fallback, StageStatus.success, TEMPLATE_PROVIDER

        prompt = narr.prompt_for(inp)
        attempts, last_error, failure = 0, None, StageStatus.provider_failure
        deadline = t0 + self.settings.llm_timeout_s * self.settings.llm_max_attempts + 5
        while attempts < self.settings.llm_max_attempts and time.perf_counter() < deadline:
            attempts += 1
            future = self._pool.submit(self.llm.complete, narr.SYSTEM_PROMPT, prompt)
            try:
                response = future.result(timeout=self.settings.llm_timeout_s)
            except FuturesTimeout:
                last_error, failure = f"Timed out after {self.settings.llm_timeout_s:g}s", StageStatus.provider_failure
                continue
            except ProviderError as exc:
                last_error, failure = str(exc), StageStatus.provider_failure
                if exc.retryable:
                    continue
                break
            except Exception as exc:  # noqa: BLE001 - provider boundary
                last_error, failure = f"{type(exc).__name__}: {exc}", StageStatus.provider_failure
                break
            try:
                parsed = narr.parse(response.text)
            except narr.InvalidNarrative as exc:
                last_error, failure = str(exc), StageStatus.invalid_result
                prompt = narr.prompt_for(inp) + f"\n\nYour previous reply was rejected: {exc}. Return only the JSON object."
                continue
            record(StageStatus.success, self.llm.info, attempts)
            return parsed, StageStatus.success, self.llm.info

        if mode == ExecutionMode.auto:
            record(StageStatus.deterministic_fallback, TEMPLATE_PROVIDER, attempts, last_error,
                   reason=f"LLM {failure.value} after {attempts} attempt(s); using deterministic narrative")
            return fallback, StageStatus.deterministic_fallback, TEMPLATE_PROVIDER
        # aws mode: report the failure. The deterministic text is still shown, but labelled as such.
        record(failure, self.llm.info, attempts, last_error, reason="Deterministic narrative displayed; LLM output unavailable")
        return fallback, failure, TEMPLATE_PROVIDER

    # ----------------------------------------------------------------- records
    def _persist(self, run, machine, diag, prog, safety, maint, narrative, n_status, n_provider) -> Incident:
        now = utcnow()
        st = self.store
        with st.lock:
            inc = st.open_incident_for(machine.id)
            hyp = diag.hypotheses[0] if diag.hypotheses else None
            fields = dict(severity=diag.severity, affected_component_id=prog.affected_component_id,
                          fault_mode_id=hyp.fault_mode_id if hyp else None, updated_at=now, diagnostics=diag,
                          prognostics=prog, safety=safety, maintenance=maint, narrative=narrative,
                          narrative_provider=n_provider, narrative_status=n_status)
            if inc is None:
                inc = Incident(id=st.next_id("INC"), machine_id=machine.id, status="open", created_at=now,
                               run_ids=[run.id], action_ids=[], requisition_id=None, work_order_id=None,
                               notification_ids=[], **fields)
            else:
                inc = inc.model_copy(update={**fields, "run_ids": [*inc.run_ids, run.id]})
            if maint is not None:
                self._sync_records(inc, machine, maint, safety, now)
            st.incidents[inc.id] = inc
            return inc

    def _sync_records(self, inc: Incident, machine, maint: MaintenanceProposal, safety: SafetyAssessment, now) -> None:
        st = self.store
        window = maint.maintenance_window
        if maint.proposed_part:
            req = st.requisitions.get(inc.requisition_id) if inc.requisition_id else None
            if req is None:
                req = Requisition(id=st.next_id("REQ"), incident_id=inc.id, sku="", description="", quantity=1,
                                  estimated_cost_usd=None, status=RecordStatus.awaiting_approval, simulated=True,
                                  created_at=now)
                inc.requisition_id = req.id
            if req.status == RecordStatus.awaiting_approval:
                req = req.model_copy(update=dict(sku=maint.proposed_part.sku, description=maint.proposed_part.description,
                                                 quantity=maint.quantity, estimated_cost_usd=maint.estimated_cost_usd))
            st.requisitions[req.id] = req
        wo = st.work_orders.get(inc.work_order_id) if inc.work_order_id else None
        if wo is None:
            wo = WorkOrder(id=st.next_id("WO"), incident_id=inc.id, machine_id=machine.id, component_id=maint.component_id,
                           title="", priority="", status=RecordStatus.awaiting_approval, simulated=True,
                           window_start=None, window_end=None, created_at=now)
            inc.work_order_id = wo.id
        if wo.status == RecordStatus.awaiting_approval:
            wo = wo.model_copy(update=dict(title=maint.work_order.title, priority=maint.work_order.priority,
                                           window_start=window.start if window else None,
                                           window_end=window.end if window else None))
        st.work_orders[wo.id] = wo

        targets = {ActionKind.submit_requisition: inc.requisition_id, ActionKind.dispatch_work_order: inc.work_order_id}
        titles = {ActionKind.submit_requisition: "Submit purchase requisition (simulated)",
                  ActionKind.dispatch_work_order: "Dispatch work order to maintenance queue (simulated)"}
        existing = {st.actions[a].kind: st.actions[a] for a in inc.action_ids}
        for policy in safety.required_approvals:
            target = targets.get(policy.action_kind)
            if target is None:
                continue
            act = existing.get(policy.action_kind)
            if act is None:
                act = ProposedAction(
                    id=st.next_id("ACT"), incident_id=inc.id, kind=policy.action_kind,
                    title=titles[policy.action_kind], target_id=target, status=ActionStatus.awaiting_approval,
                    approvals=[ApprovalRecord(role=r) for r in policy.roles],
                    requires_isolation_attestation=policy.requires_isolation_attestation,
                    created_at=now, updated_at=now)
                inc.action_ids.append(act.id)
            elif act.status == ActionStatus.awaiting_approval:
                # Safety gates only ever tighten: keep decisions, add newly required roles.
                have = {a.role for a in act.approvals}
                added = [ApprovalRecord(role=r) for r in policy.roles if r not in have]
                if added:
                    act = act.model_copy(update=dict(approvals=[*act.approvals, *added], updated_at=now))
                if policy.requires_isolation_attestation and not act.requires_isolation_attestation:
                    act = act.model_copy(update=dict(requires_isolation_attestation=True))
            st.actions[act.id] = act

    # -------------------------------------------------------------- activity
    def site_time(self):
        """Latest replay time across machines (the site's 'now' for orders not tied to one incident)."""
        times = []
        for mid in self.ref.machines:
            c = self.cursor(mid)
            pts = self.telemetry.window(mid, c, c).points
            if pts:
                times.append(pts[-1].timestamp)
        return max(times) if times else None

    def machine_time(self, incident_id: str):
        """Replay clock for an incident's machine (the timestamp at the current cursor)."""
        inc = self.store.incidents.get(incident_id)
        if inc is None:
            return None
        c = self.cursor(inc.machine_id)
        pts = self.telemetry.window(inc.machine_id, c, c).points
        return pts[-1].timestamp if pts else None

    def _log_progress(self, inc: Incident, before: Incident | None, machine, n_input: NarrativeInput, as_of) -> None:
        log = lambda kind, text: self.store.log(inc.id, "ghostshift", "GhostShift", kind, text, as_of)  # noqa: E731
        comp = next((c.name.lower() for c in machine.components if c.id == inc.affected_component_id), "machine")
        hyp = inc.diagnostics.hypotheses[0] if inc.diagnostics.hypotheses else None
        if before is None:
            what = f"likely {hyp.name.lower()}" if hyp else f"unusual readings on the {comp}"
            log("detected", f"Spotted {what}: {n_input.sms_finding[0].lower()}{n_input.sms_finding[1:]}")
        tier = inc.safety.risk_tier
        if before is None or TIER_RANK[tier] > TIER_RANK[before.safety.risk_tier]:
            log("priority", f"Set priority to {PRIORITY[tier]}: {inc.safety.rationale[0][0].lower()}{inc.safety.rationale[0][1:]}")
        if inc.requisition_id and (before is None or not before.requisition_id):
            req = self.store.requisitions[inc.requisition_id]
            log("drafted", f"Picked part {req.sku} and drafted order {req.id}")
        if inc.work_order_id and (before is None or not before.work_order_id):
            w = inc.maintenance.maintenance_window if inc.maintenance else None
            slot = f"{w.label.lower()} ({w.start:%a %H:%M} UTC)" if w else "a slot once one fits"
            log("scheduled", f"Proposed {slot} and drafted work order {inc.work_order_id}")

    def _autopilot(self, inc: Incident, as_of) -> list[str] | None:
        """Place eligible parts orders without a person. Returns notes, or None when autopilot is off.

        Policy (deterministic): High or Urgent priority, only the maintenance supervisor's approval
        required, cost within the auto-order limit, and the part in stock or arriving before the
        earliest estimated limit. Physical work is never released automatically.
        """
        a = self.store.autonomy
        if a is None or a.level != AutonomyLevel.autopilot or self.approvals is None:
            return None
        notes: list[str] = []
        for act_id in list(inc.action_ids):
            act = self.store.actions[act_id]
            if act.status != ActionStatus.awaiting_approval:
                continue
            if act.kind == ActionKind.dispatch_work_order:
                self._log_once(inc, "handoff", f"Left work order {act.target_id} for a supervisor: physical work needs "
                                               "a lockout/tagout sign-off", as_of)
                continue
            ok, reason = self._can_auto_order(inc, act, a.auto_order_limit_usd)
            if not ok:
                notes.append(reason)
                self._log_once(inc, "held", f"Held the parts order: {reason}", as_of)
                continue
            self.approvals.decide(act.id, DecisionRequest(
                role=ApproverRole.maintenance_supervisor, approver_name=AUTO_ORDER_NAME, decision="approve",
                note=reason), automated=True)
            self.approvals.execute(act.id, actor="policy", actor_name=AUTO_ORDER_NAME)
            notes.append(f"Ordered automatically: {reason}")
        return notes

    def _can_auto_order(self, inc: Incident, act: ProposedAction, limit: float) -> tuple[bool, str]:
        if TIER_RANK[inc.safety.risk_tier] < TIER_RANK[RiskTier.high]:
            return False, "waiting until priority is High"
        if [r.role for r in act.approvals] != [ApproverRole.maintenance_supervisor]:
            return False, "this order also needs the operations manager"
        req = self.store.requisitions[act.target_id]
        if req.estimated_cost_usd is None or req.estimated_cost_usd > limit:
            cost = "unknown cost" if req.estimated_cost_usd is None else f"${req.estimated_cost_usd:,.0f}"
            return False, f"{cost} is over the ${limit:,.0f} auto-order limit"
        part = inc.maintenance.proposed_part if inc.maintenance else None
        if part is None:
            return False, "no matching part"
        avail = part.availability
        rul = inc.prognostics.rul
        if (avail.on_hand or 0) >= req.quantity:
            when = "in stock"
        elif avail.lead_time_days is not None and rul and rul.supportable and rul.lower_hours is not None \
                and avail.lead_time_days * 24 <= rul.lower_hours:
            when = f"arrives in {avail.lead_time_days:g} d, before the earliest limit"
        else:
            return False, "the part might not arrive before the limit"
        return True, f"within the ${limit:,.0f} limit, {when}"

    def _log_once(self, inc: Incident, kind: str, text: str, as_of) -> None:
        if not any(e.kind == kind and e.text == text for e in self.store.activity_for(inc.id)):
            self.store.log(inc.id, "ghostshift", "GhostShift", kind, text, as_of)

    def autopilot_sweep(self) -> None:
        """Apply the autonomy setting to open incidents right away (e.g. after it is switched on)."""
        for inc in [i for i in self.store.incidents.values() if i.status == "open"]:
            self._autopilot(inc, self.machine_time(inc.id))

    # ------------------------------------------------------------ notification
    def _notify(self, run: WorkflowRun, machine, incident: Incident, n_input: NarrativeInput, as_of=None) -> None:
        tier = incident.safety.risk_tier
        prev = self.store.notified_tier.get(incident.id)
        if not incident.safety.notify_technician:
            run.stages.append(self._skipped("notification", f"Tier '{tier.value}' does not require technician SMS"))
            return
        if prev is not None and TIER_RANK[RiskTier(prev)] >= TIER_RANK[tier]:
            run.stages.append(self._skipped("notification", f"Technician already notified at tier '{prev}'"))
            return
        tech = self.ref.technicians.get(machine.id)
        if tech is None:
            run.stages.append(self._skipped("notification", "No technician configured for this machine"))
            return

        token, _grant = self.store.issue_grant(incident.id, self.settings.inspection_token_ttl_hours)
        url = f"{self.settings.public_base_url}/m/{token}"
        comp = next((c.name for c in machine.components if c.id == incident.affected_component_id), "component")
        lead = "ESCALATED to " if prev else ""
        req = self.store.requisitions.get(incident.requisition_id) if incident.requisition_id else None
        ordered = " Part ordered." if req and req.status in (RecordStatus.submitted, RecordStatus.submitted_simulated) else ""
        body = (f"GhostShift {lead}{tier.value.upper()}: {machine.id} {comp.lower()} - "
                f"{incident.narrative.sms_key_finding}. {n_input.rul_text.capitalize()}.{ordered} Open: {url}")

        result, rec = self._stage("notification", self.sms.info, lambda: self.sms.send(to=tech.phone, body=body))
        if result is None:
            status, attempts, error, ext = NotificationStatus.failed, 1, rec.error, None
        else:
            attempts, error, ext = result.attempts, result.error, result.external_id
            if result.skipped:
                status = NotificationStatus.skipped
            elif result.delivered:
                status = NotificationStatus.simulated_sent if result.simulated else NotificationStatus.sent
            else:
                status = NotificationStatus.failed
            rec.attempts = max(1, attempts)
            if status in (NotificationStatus.failed, NotificationStatus.skipped):
                rec.status, rec.error = StageStatus.provider_failure, error
        run.stages.append(rec)

        note = Notification(
            id=self.store.next_id("SMS"), incident_id=incident.id, channel="sms", recipient_label=tech.label,
            to_masked=_mask(tech.phone if self.sms.info.kind != ProviderKind.external
                            else (self.settings.demo_technician_phone or tech.phone)),
            body=body, inspection_url=url, status=status, provider=self.sms.info, attempts=attempts, error=error,
            external_id=ext, created_at=utcnow())
        with self.store.lock:
            self.store.notifications[note.id] = note
            inc = self.store.incidents[incident.id]
            inc.notification_ids.append(note.id)
            if status in (NotificationStatus.sent, NotificationStatus.simulated_sent):
                self.store.notified_tier[incident.id] = tier.value
        who = tech.label.split(" · ")[0]
        if status in (NotificationStatus.sent, NotificationStatus.simulated_sent):
            text = f"Texted {who} a link to the technician view" + (" (simulated)" if status == NotificationStatus.simulated_sent else "")
        else:
            text = f"Text to {who} was not sent: {error}"
        self.store.log(incident.id, "ghostshift", "GhostShift", "notified", text, as_of)


def _mask(phone: str) -> str:
    return f"{phone[:2]} ••• ••• ••{phone[-2:]}" if len(phone) > 6 else "••••"
