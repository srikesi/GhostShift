"""GhostMode copilot: the chat agent that coordinates GhostShift's specialist agents.

A Bedrock model (Converse tool use) answers questions about a machine or incident by
calling read-only tools. Each tool is a thin wrapper over an existing specialist
(diagnostics, prognostics, safety supervisor, maintenance & supply) or over the
schedule and inventory services. The model decides which specialists to consult and
combines their answers; it never decides anything itself.

Guarantees, enforced in code:
- Read-only. No tool can approve, reject or execute an action, change a priority,
  order a part or send a message. Unknown tool names are refused as tool errors.
- Bounded. At most MAX_TOOL_CALLS tool calls and MAX_TURNS model turns per question.
- Honest status. `success` = model answer; `deterministic_fallback` = built-in answer
  because the model was unavailable or failed (auto mode); `provider_failure` /
  `invalid_result` = the failure is reported (aws mode).
- Answers claiming equipment is safe or isolated are rejected (narrative.FORBIDDEN).

Without a model (demo mode) the copilot answers a few common questions from the same
tools with built-in rules, clearly labelled.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..integrations.base import ProviderError, info
from ..schemas.agents import PrognosticsInput
from ..schemas.common import ProviderKind, Severity, StageStatus
from ..schemas.copilot import ChatTurn, CopilotAnswer, ToolCallRecord
from .narrative import FORBIDDEN

MAX_TOOL_CALLS = 6
MAX_TURNS = 8
BUILT_IN = info("copilot-built-in", ProviderKind.deterministic)
PRIORITY = {"routine": "Low", "elevated": "Medium", "high": "High", "critical": "Urgent"}
SUGGESTED = [
    "Why was this flagged?",
    "What happens if we wait until the weekend?",
    "Which other parts should we check?",
]

SYSTEM_PROMPT = """You are GhostMode, the shift manager's assistant for GhostShift, a data center
maintenance system. You help operators, new engineers, technicians and supervisors understand
equipment problems and decide what to do next.

How you work
- Answer only from tool results. Call the specialist tools, combine what they return, and
  explain it in plain words for the person's experience level. Prefer 2-4 tool calls.
- Quote numbers exactly as the tools return them, with units. If no tool gives a value, say
  you do not have it. Never estimate or invent readings, dates, prices or stock.
- Say which specialist each key fact came from (diagnostics, prognostics, safety supervisor,
  maintenance & supply, schedule, inventory).
- Keep answers short: a direct answer first, then up to 5 short bullet points.
- If the person seems new, explain a term once and say what to check first.

What you must never do
- Never approve, reject or execute an action, change a priority, order a part, send a
  message, or release physical work. You have no tools for these: say a supervisor does it
  in GhostShift.
- Never say equipment is safe, isolated or de-energised. Work needs the site lockout/tagout
  procedure and a qualified person. Say so when relevant.
- If a tool fails or returns an error, say so. Do not fill the gap.
- If you are unsure, say what you checked and what is missing."""


# ------------------------------------------------------------------ tool inputs
class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NoInput(_In):
    pass


class MachineInput(_In):
    machine_id: str = Field(description="Machine id, e.g. MF-07 or CH-02")


class SensorInput(_In):
    machine_id: str = Field(description="Machine id, e.g. MF-07 or CH-02")
    sensor_id: str | None = Field(None, description="One sensor id; omit for every sensor on the machine")


class PartsInput(_In):
    machine_id: str = Field(description="Machine id, e.g. MF-07 or CH-02")
    component_id: str | None = Field(None, description="Component id; omit for the affected component")


class InventoryInput(_In):
    sku: str | None = Field(None, description="Part number (SKU); omit for all stock")


class Tool:
    def __init__(self, name: str, agent: str, description: str, model: type[_In], fn: Callable[[Any], dict]):
        self.name, self.agent, self.description, self.model, self.fn = name, agent, description, model, fn

    def spec(self) -> dict:
        schema = self.model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
            if "anyOf" in prop:  # Optional[str] -> plain string; omitted means "all"
                prop.pop("anyOf")
                prop.pop("default", None)
                prop["type"] = "string"
        schema.setdefault("properties", {})
        schema["type"] = "object"
        return {"toolSpec": {"name": self.name, "description": self.description, "inputSchema": {"json": schema}}}


class ToolError(Exception):
    """Returned to the model as a tool error (it can correct itself)."""


# ------------------------------------------------------------------ the tools
class CopilotTools:
    """Read-only views over GhostShift's specialists. `deps` is the app container (duck-typed)."""

    def __init__(self, deps):
        self.d = deps
        self.tools: dict[str, Tool] = {t.name: t for t in [
            Tool("list_machines", "site", "List the monitored machines with their condition and any open problem.",
                 NoInput, self.list_machines),
            Tool("get_machine_status", "diagnostics",
                 "Current condition of one machine: overall condition, open problem and priority, and the health "
                 "of each component.", MachineInput, self.get_machine_status),
            Tool("get_sensor_readings", "diagnostics",
                 "Latest sensor readings compared with the machine's own normal range and its alert/danger limits.",
                 SensorInput, self.get_sensor_readings),
            Tool("run_diagnostics", "diagnostics",
                 "Run the diagnostics specialist now: which readings are abnormal and which known fault pattern "
                 "they match, with the conditions that matched or did not.", MachineInput, self.run_diagnostics),
            Tool("get_time_to_limit", "prognostics",
                 "Run the prognostics specialist: estimated time until the danger limit (as a range, only when "
                 "the trend is clear), failure risk, and service due dates per component.",
                 MachineInput, self.get_time_to_limit),
            Tool("get_incident", "safety supervisor",
                 "The open problem on a machine: priority and why, escalation rules, required approvals and their "
                 "status, proposed part, maintenance slot and work-order steps.", MachineInput, self.get_incident),
            Tool("search_parts", "maintenance & supply",
                 "Parts that fit a component, ranked by fit, with price, stock and lead time.",
                 PartsInput, self.search_parts),
            Tool("get_maintenance_windows", "maintenance & supply",
                 "Upcoming planned downtime windows for a machine, the redundant unit that must stay running, and "
                 "any booked or held repair slot.", MachineInput, self.get_maintenance_windows),
            Tool("get_inventory", "inventory",
                 "Spare-parts stock, open purchase orders and reorder suggestions (simulated).",
                 InventoryInput, self.get_inventory),
        ]}

    def specs(self) -> list[dict]:
        return [t.spec() for t in self.tools.values()]

    def call(self, name: str, raw: Any) -> tuple[Tool | None, dict]:
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError(f"Unknown tool '{name}'. You only have these read-only tools: "
                            f"{', '.join(self.tools)}. Approvals, orders and messages are done by people.")
        try:
            args = tool.model.model_validate(raw or {})
        except ValidationError as exc:
            raise ToolError(f"Invalid input for {name}: {exc.errors()[:3]}") from exc
        return tool, tool.fn(args)

    # helpers
    def _machine(self, machine_id: str):
        machines = self.d.reference.machines
        if machine_id not in machines:
            raise ToolError(f"Machine '{machine_id}' not found. Known machines: {', '.join(machines)}")
        return self.d.reference.machine(machine_id)

    def _now(self, machine_id: str):
        pts = self.d.orchestrator.window(machine_id).points
        return pts[-1].timestamp if pts else None

    def _prognostics(self, machine_id: str):
        m = self._machine(machine_id)
        o = self.d.orchestrator
        s = o.screen(machine_id)
        w = o.window(machine_id)
        return s, o.prognostics.run(PrognosticsInput(machine=m, window=w, diagnostics=s.diagnostics,
                                                     as_of=w.points[-1].timestamp))

    # tools
    def list_machines(self, _: NoInput) -> dict:
        out = []
        for mid, m in self.d.reference.machines.items():
            s = self.d.orchestrator.screen(mid)
            inc = self.d.store.open_incident_for(mid)
            out.append({"machine_id": mid, "name": m.display_name, "type": m.machine_type,
                        "condition": s.diagnostics.severity.value,
                        "open_problem": inc.id if inc else None,
                        "priority": PRIORITY[inc.safety.risk_tier.value] if inc else None})
        return {"machines": out}

    def get_machine_status(self, a: MachineInput) -> dict:
        m = self._machine(a.machine_id)
        s, prog = self._prognostics(a.machine_id)
        inc = self.d.store.open_incident_for(a.machine_id)
        names = {c.id: c.name for c in m.components}
        return {
            "machine_id": m.id, "name": m.display_name, "model": m.model, "as_of": str(self._now(m.id)),
            "condition": s.diagnostics.severity.value,
            "open_problem": None if inc is None else {
                "incident_id": inc.id, "priority": PRIORITY[inc.safety.risk_tier.value],
                "headline": inc.narrative.headline},
            "components": [{"component_id": h.component_id, "name": names.get(h.component_id, h.component_id),
                            "condition": h.status.value, "summary": h.summary} for h in prog.component_health],
        }

    def get_sensor_readings(self, a: SensorInput) -> dict:
        self._machine(a.machine_id)
        sensors = self.d.orchestrator.screen(a.machine_id).diagnostics.sensors
        if a.sensor_id:
            sensors = [x for x in sensors if x.sensor_id == a.sensor_id]
            if not sensors:
                raise ToolError(f"Sensor '{a.sensor_id}' not found on {a.machine_id}")
        return {"machine_id": a.machine_id, "as_of": str(self._now(a.machine_id)), "sensors": [{
            "sensor_id": x.sensor_id, "name": x.sensor_name, "unit": x.unit, "component_id": x.component_id,
            "latest": round(x.latest_value, 3), "recent_mean": round(x.recent_mean, 3),
            "normal_mean": round(x.baseline.mean, 3), "normal_std": round(x.baseline.std, 3),
            "change_vs_normal_pct": round(x.pct_change, 1), "trend_per_hour": round(x.slope_per_hour, 4),
            "alert_limit": x.alert_limit, "danger_limit": x.danger_limit, "limit_state": x.limit_state.value,
            "condition": x.severity.value, "abnormal": x.anomalous} for x in sensors]}

    def run_diagnostics(self, a: MachineInput) -> dict:
        self._machine(a.machine_id)
        d = self.d.orchestrator.screen(a.machine_id).diagnostics
        return {"machine_id": a.machine_id, "condition": d.severity.value,
                "abnormal_readings": [x.description for x in d.anomalies],
                "fault_patterns": [{"name": h.name, "component_id": h.component_id,
                                    "confidence": round(h.confidence, 2), "matched": h.matched_conditions,
                                    "not_matched": h.unmatched_conditions,
                                    "contradicting": h.contradicting_conditions} for h in d.hypotheses],
                "warnings": d.warnings, "method": d.method}

    def get_time_to_limit(self, a: MachineInput) -> dict:
        _, prog = self._prognostics(a.machine_id)
        r = prog.rul
        rul = None if r is None else {
            "component_id": r.component_id, "sensor_id": r.sensor_id, "trend_is_clear": r.supportable,
            "earliest_hours": r.lower_hours, "estimate_hours": r.value_hours, "latest_hours": r.upper_hours,
            "danger_limit": r.threshold, "note": r.confidence_note, "limitations": r.limitations}
        return {"machine_id": a.machine_id, "as_of": str(self._now(a.machine_id)),
                "affected_component_id": prog.affected_component_id, "time_to_danger_limit": rul,
                "failure_risk": {"score": prog.failure_risk.score, "band": prog.failure_risk.band,
                                 "horizon_hours": prog.failure_risk.horizon_hours,
                                 "calibrated": prog.failure_risk.calibrated},
                "service_due": [{"component_id": h.component_id, "hours": h.rul.value_hours,
                                 "basis": h.rul.basis_note} for h in prog.component_health if h.rul],
                "limitations": prog.limitations}

    def get_incident(self, a: MachineInput) -> dict:
        self._machine(a.machine_id)
        st = self.d.store
        inc = st.open_incident_for(a.machine_id)
        if inc is None:
            return {"machine_id": a.machine_id, "open_problem": None,
                    "note": "No open problem on this machine. Readings are within their normal ranges."}
        actions = [st.actions[i] for i in inc.action_ids if i in st.actions]
        m = inc.maintenance
        booking = next(iter(self.d.calendar.bookings(incident_id=inc.id)), None) if self.d.calendar else None
        return {
            "incident_id": inc.id, "machine_id": inc.machine_id, "priority": PRIORITY[inc.safety.risk_tier.value],
            "headline": inc.narrative.headline, "summary": inc.narrative.summary,
            "priority_reasons": inc.safety.rationale, "escalation_rules": inc.safety.escalation,
            "recommended_response": inc.safety.recommended_response, "safety_notices": inc.safety.safety_notices,
            "approvals": [{"action": x.title, "status": x.status.value,
                           "roles_needed": [r.role.value for r in x.approvals],
                           "approved_by": [r.role.value for r in x.approvals if r.decision.value == "approved"],
                           "needs_lockout_tagout_attestation": x.requires_isolation_attestation} for x in actions],
            "proposed_part": None if not (m and m.proposed_part) else {
                "sku": m.proposed_part.sku, "description": m.proposed_part.description,
                "estimated_cost_usd": m.estimated_cost_usd, "on_hand": m.proposed_part.availability.on_hand,
                "lead_time_days": m.proposed_part.availability.lead_time_days},
            "maintenance_window": None if not (m and m.maintenance_window) else {
                "label": m.maintenance_window.label, "start": str(m.maintenance_window.start),
                "before_earliest_limit": m.maintenance_window.before_rul_lower_bound},
            "work_order_steps": [t.description for t in m.work_order.tasks] if m else [],
            "booking": None if booking is None else {
                "status": booking.status.value, "start": str(booking.start), "technician": booking.technician_name},
            "warnings": m.warnings if m else [],
        }

    def search_parts(self, a: PartsInput) -> dict:
        m = self._machine(a.machine_id)
        comp_id = a.component_id
        if comp_id is None:
            inc = self.d.store.open_incident_for(a.machine_id)
            comp_id = inc.affected_component_id if inc else None
        if comp_id is None:
            raise ToolError("No component given and no open problem; pass component_id (see get_machine_status)")
        comp = next((c for c in m.components if c.id == comp_id), None)
        if comp is None:
            raise ToolError(f"Component '{comp_id}' not found on {m.id}: {', '.join(c.id for c in m.components)}")
        parts = self.d.parts.candidates(component_type=comp.type, machine_model=m.model)
        return {"machine_id": m.id, "component_id": comp.id, "component": comp.name, "parts": [{
            "sku": p.sku, "description": p.description, "unit_cost_usd": p.unit_cost_usd,
            "on_hand": p.availability.on_hand, "lead_time_days": p.availability.lead_time_days,
            "location": p.availability.location} for p in parts], "note": "Prices and stock are simulated"}

    def get_maintenance_windows(self, a: MachineInput) -> dict:
        self._machine(a.machine_id)
        now = self._now(a.machine_id)
        windows = [w for w in self.d.reference.windows_for(a.machine_id) if now is None or w.end > now][:5]
        inc = self.d.store.open_incident_for(a.machine_id)
        bookings = self.d.calendar.bookings(incident_id=inc.id) if (inc and self.d.calendar) else []
        partner = self.d.calendar.partner_of(a.machine_id) if self.d.calendar else None
        return {"machine_id": a.machine_id, "as_of": str(now), "must_stay_running": partner,
                "windows": [{"label": w.label, "start": str(w.start), "end": str(w.end),
                             "hours_from_now": round((w.start - now).total_seconds() / 3600, 1) if now else None}
                            for w in windows],
                "bookings": [{"status": b.status.value, "start": str(b.start), "end": str(b.end),
                              "technician": b.technician_name, "window": b.window_label} for b in bookings]}

    def get_inventory(self, a: InventoryInput) -> dict:
        v = self.d.inventory.view()
        stock = [s for s in v.stock if a.sku is None or s.sku == a.sku]
        if a.sku and not stock:
            raise ToolError(f"No stock record for '{a.sku}'")
        orders = [o for o in v.open_orders if a.sku is None or o.sku == a.sku]
        return {"stock": [{"sku": s.sku, "description": s.description, "storeroom": s.storeroom,
                           "available": s.available, "reserved": s.reserved, "min": s.min} for s in stock],
                "orders": [{"id": o.id, "sku": o.sku, "status": o.status.value, "supplier": o.supplier_name,
                            "eta": str(o.eta) if o.eta else None} for o in orders[:8]],
                "reorder_suggestions": [{"sku": r.sku, "quantity": r.suggested_qty, "reason": r.reason}
                                        for r in v.reorder_suggestions if a.sku is None or r.sku == a.sku],
                "note": "Stock, suppliers and orders are simulated"}


# ------------------------------------------------------------------ the agent
class Copilot:
    name = "copilot"

    def __init__(self, tools: CopilotTools, llm, *, report_failures: bool, fallback_reason: str | None = None,
                 deadline_s: float = 60.0):
        """`llm` has `converse(...)` (BedrockConverseLLM) or is None (built-in answers only).

        report_failures: aws mode (failures are reported, never replaced by a built-in answer).
        fallback_reason: why there is no model (shown when answering with built-in rules).
        """
        self.tools = tools
        self.llm = llm
        self.report_failures = report_failures
        self.fallback_reason = fallback_reason
        self.deadline_s = deadline_s

    def ask(self, *, machine_id: str, question: str, incident_id: str | None = None,
            history: list[ChatTurn] | None = None) -> CopilotAnswer:
        self.tools._machine(machine_id)  # ToolError -> 404 at the API
        inc = self.tools.d.store.open_incident_for(machine_id)
        incident_id = incident_id or (inc.id if inc else None)
        if self.llm is None:
            return self._built_in(machine_id, incident_id, question, status=StageStatus.success
                                  if self.fallback_reason is None else StageStatus.deterministic_fallback,
                                  error=self.fallback_reason)
        calls: list[ToolCallRecord] = []
        try:
            text = self._loop(machine_id, incident_id, question, history or [], calls)
        except ProviderError as exc:
            return self._failed(machine_id, incident_id, question, calls, StageStatus.provider_failure, str(exc))
        if not text.strip():
            return self._failed(machine_id, incident_id, question, calls, StageStatus.invalid_result,
                                "The model returned no answer")
        if FORBIDDEN.search(text):
            return self._failed(machine_id, incident_id, question, calls, StageStatus.invalid_result,
                                "The model's answer claimed equipment is safe or isolated, so it was rejected")
        return CopilotAnswer(machine_id=machine_id, incident_id=incident_id, answer=text.strip(), tool_calls=calls,
                             status=StageStatus.success, provider=self.llm.info, built_in=False,
                             suggested_questions=SUGGESTED)

    # -- model loop
    def _loop(self, machine_id: str, incident_id: str | None, question: str, history: list[ChatTurn],
              calls: list[ToolCallRecord]) -> str:
        now = self.tools._now(machine_id)
        context = (f"[Context: the person is looking at machine {machine_id}"
                   + (f", open problem {incident_id}" if incident_id else ", no open problem")
                   + (f". Site time is {now:%a %d %b %H:%M} UTC" if now else "") + ".]\n")
        messages = _history_messages(history)
        messages.append({"role": "user", "content": [{"text": context + question}]})
        specs = self.tools.specs()
        started = time.perf_counter()
        for _turn in range(MAX_TURNS):
            if time.perf_counter() - started > self.deadline_s:
                raise ProviderError(f"Copilot took longer than {self.deadline_s:g}s")
            resp = self.llm.converse(system=SYSTEM_PROMPT, messages=messages, tools=specs)
            msg = resp["message"]
            content = [b for b in msg.get("content", []) if isinstance(b, dict)]
            messages.append({"role": "assistant", "content": content})
            uses = [b["toolUse"] for b in content if "toolUse" in b]
            text = "".join(b.get("text", "") for b in content if "text" in b)
            if not uses:
                return text
            results = []
            for use in uses:
                results.append(self._run_tool(use, calls))
            messages.append({"role": "user", "content": results})
        raise ProviderError(f"No final answer after {MAX_TURNS} model turns")

    def _run_tool(self, use: dict, calls: list[ToolCallRecord]) -> dict:
        name, tool_id, raw = use.get("name", ""), use.get("toolUseId", ""), use.get("input") or {}
        t0 = time.perf_counter()
        tool = self.tools.tools.get(name)
        agent = tool.agent if tool else "none"
        if len(calls) >= MAX_TOOL_CALLS:
            ok, payload, summary = False, {"error": f"Tool limit of {MAX_TOOL_CALLS} reached. Answer now with "
                                                    "what you have, and say what you could not check."}, \
                "Refused: tool limit reached"
        else:
            try:
                _, payload = self.tools.call(name, raw)
                ok, summary = True, _summarize(name, payload)
            except ToolError as exc:
                ok, payload, summary = False, {"error": str(exc)}, f"Error: {exc}"
            except Exception as exc:  # noqa: BLE001 - a broken tool must not crash the chat
                ok, payload, summary = False, {"error": f"{type(exc).__name__}: {exc}"}, f"Failed: {exc}"
        calls.append(ToolCallRecord(name=name, agent=agent, input=raw if isinstance(raw, dict) else {"raw": raw},
                                    ok=ok, summary=summary[:300],
                                    duration_ms=round((time.perf_counter() - t0) * 1000, 1)))
        result: dict[str, Any] = {"toolUseId": tool_id, "content": [{"text": json.dumps(payload, default=str)}]}
        if not ok:
            result["status"] = "error"
        return {"toolResult": result}

    def _failed(self, machine_id, incident_id, question, calls, status: StageStatus, error: str) -> CopilotAnswer:
        if self.report_failures:  # aws mode: report, never mask
            return CopilotAnswer(machine_id=machine_id, incident_id=incident_id,
                                 answer=f"The copilot could not answer: {error}", tool_calls=calls, status=status,
                                 provider=self.llm.info, built_in=False, error=error,
                                 suggested_questions=SUGGESTED)
        out = self._built_in(machine_id, incident_id, question, status=StageStatus.deterministic_fallback,
                             error=error)
        return out.model_copy(update={"tool_calls": [*calls, *out.tool_calls]})

    # -- built-in answers (no model)
    def _built_in(self, machine_id: str, incident_id: str | None, question: str, *, status: StageStatus,
                  error: str | None) -> CopilotAnswer:
        calls: list[ToolCallRecord] = []

        def use(name: str, **kw) -> dict:
            return json.loads(self._run_tool({"name": name, "toolUseId": name, "input": kw}, calls)
                              ["toolResult"]["content"][0]["text"])

        q = question.lower()
        if any(w in q for w in ("wait", "weekend", "defer", "delay", "later", "postpone")):
            answer = _answer_wait(use("get_time_to_limit", machine_id=machine_id),
                                  use("get_maintenance_windows", machine_id=machine_id))
        elif any(w in q for w in ("other part", "which part", "check", "inspect", "component")):
            answer = _answer_parts(use("get_machine_status", machine_id=machine_id),
                                   use("get_time_to_limit", machine_id=machine_id))
        else:
            answer = _answer_why(use("get_incident", machine_id=machine_id),
                                 use("run_diagnostics", machine_id=machine_id),
                                 use("get_time_to_limit", machine_id=machine_id))
        if not any(w in q for w in ("why", "flag", "wait", "weekend", "defer", "delay", "later", "postpone",
                                    "other part", "which part", "check", "inspect", "component")):
            answer = ("Built-in answers cover a few common questions; connect Bedrock for anything else. "
                      "Here is the current picture:\n\n" + answer)
        return CopilotAnswer(machine_id=machine_id, incident_id=incident_id, answer=answer, tool_calls=calls,
                             status=status, provider=BUILT_IN, built_in=True, error=error,
                             suggested_questions=SUGGESTED)


# ------------------------------------------------------------------ helpers
def _history_messages(history: list[ChatTurn]) -> list[dict]:
    """Earlier turns as Converse messages: must start with a user turn and alternate."""
    out: list[dict] = []
    for t in history[-10:]:
        if not out and t.role != "user":
            continue
        if out and out[-1]["role"] == t.role:
            out[-1]["content"][0]["text"] += "\n" + t.text
        else:
            out.append({"role": t.role, "content": [{"text": t.text}]})
    if out and out[-1]["role"] == "user":  # the new question is the next user turn
        out.pop()
    return out


def _summarize(name: str, p: dict) -> str:
    if name == "list_machines":
        return f"{len(p['machines'])} machines"
    if name == "get_machine_status":
        prob = p.get("open_problem")
        return f"{p['machine_id']}: {p['condition']}" + (f", {prob['priority']} priority" if prob else "")
    if name == "get_sensor_readings":
        bad = [s["name"] for s in p["sensors"] if s["abnormal"]]
        return f"{len(p['sensors'])} sensors" + (f"; abnormal: {', '.join(bad[:3])}" if bad else "; all normal")
    if name == "run_diagnostics":
        top = p["fault_patterns"][0]["name"] if p["fault_patterns"] else "no known pattern"
        return f"{p['condition']}; {top}"
    if name == "get_time_to_limit":
        r = p.get("time_to_danger_limit")
        if r and r["trend_is_clear"] and r["earliest_hours"] is not None:
            return f"{r['earliest_hours']:.0f}–{(r['latest_hours'] or 0):.0f} h to the danger limit"
        return "trend not clear enough for an estimate"
    if name == "get_incident":
        return f"{p['incident_id']}, {p['priority']} priority" if p.get("incident_id") else "no open problem"
    if name == "search_parts":
        return f"{len(p['parts'])} parts for {p['component']}"
    if name == "get_maintenance_windows":
        return f"{len(p['windows'])} upcoming windows"
    if name == "get_inventory":
        return f"{len(p['stock'])} stock lines, {len(p['orders'])} orders"
    return "ok"


def _hours(h) -> str:
    return "—" if h is None else (f"{h / 24:.1f} days" if h >= 48 else f"{h:.0f} h")


def _answer_why(inc: dict, diag: dict, ttl: dict) -> str:
    if "error" in inc or not inc.get("incident_id"):
        if diag.get("condition") == "normal":
            return "Nothing is flagged on this machine: every reading is inside its normal range (diagnostics)."
    lines = []
    pats = diag.get("fault_patterns") or []
    if inc.get("incident_id"):
        lines.append(f"{inc['machine_id']} is at {inc['priority']} priority: {inc['headline']}")
    if pats:
        p = pats[0]
        lines.append(f"• Diagnostics matched {p['name']} (confidence {p['confidence']:.0%}): "
                     + "; ".join(p["matched"][:3]))
    for r in (diag.get("abnormal_readings") or [])[:2]:
        lines.append(f"• {r}")
    r = ttl.get("time_to_danger_limit")
    if r and r["trend_is_clear"] and r["earliest_hours"] is not None:
        lines.append(f"• Prognostics: about {_hours(r['earliest_hours'])} to {_hours(r['latest_hours'])} "
                     "until the danger limit at the current trend.")
    else:
        lines.append("• Prognostics: the trend is not clear enough yet to estimate time to the danger limit.")
    for reason in (inc.get("priority_reasons") or [])[:1]:
        lines.append(f"• Safety supervisor: {reason}")
    lines.append("Work on the unit needs the site lockout/tagout procedure and a qualified person.")
    return "\n".join(lines)


def _answer_wait(ttl: dict, win: dict) -> str:
    r = ttl.get("time_to_danger_limit")
    windows = win.get("windows") or []
    if not (r and r["trend_is_clear"] and r["earliest_hours"] is not None):
        head = ("Prognostics cannot estimate time to the danger limit yet (the trend is not clear), so there "
                "is no evidence either way on waiting. Keep watching the readings.")
        return head + ("\n" + "\n".join(f"• {w['label']}: in {_hours(w['hours_from_now'])}" for w in windows[:3])
                       if windows else "")
    early = r["earliest_hours"]
    lines = [f"Prognostics puts the danger limit {_hours(early)} to {_hours(r['latest_hours'])} away "
             f"(earliest {_hours(early)})."]
    for w in windows[:4]:
        h = w["hours_from_now"]
        verdict = "before the earliest limit" if h is not None and h < early else "AFTER the earliest limit"
        lines.append(f"• {w['label']}: starts in {_hours(h)}, {verdict}")
    late = [w for w in windows if w["hours_from_now"] is not None and w["hours_from_now"] >= early]
    if late:
        lines.append("Waiting for a window that starts after the earliest limit risks reaching the danger limit "
                     "first. Operations would need to decide on an earlier stop.")
    if win.get("must_stay_running"):
        lines.append(f"{win['must_stay_running']} must stay running while this unit is down.")
    return "\n".join(lines)


def _answer_parts(status: dict, ttl: dict) -> str:
    comps = status.get("components") or []
    flagged = [c for c in comps if c["condition"] != Severity.normal.value]
    lines = []
    if flagged:
        lines.append("Components that are not normal (diagnostics / prognostics):")
        lines += [f"• {c['name']}: {c['condition']}. {c['summary']}" for c in flagged]
    else:
        lines.append("No other components are outside their normal range.")
    skip = {c["component_id"] for c in flagged}
    due = sorted([d for d in ttl.get("service_due") or [] if d.get("hours") is not None
                  and d["component_id"] not in skip], key=lambda d: d["hours"])[:3]
    names = {c["component_id"]: c["name"] for c in comps}
    if due:
        lines.append("Other parts, next service due:")
        lines += [f"• {names.get(d['component_id'], d['component_id'])}: due in {_hours(d['hours'])}" for d in due]
    return "\n".join(lines)

