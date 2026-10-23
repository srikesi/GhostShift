"""Incident narrative: deterministic template plus optional LLM wording.

The LLM only rewords findings the deterministic agents already produced. Its
output schema has no tier, approval or action fields, and outputs that claim the
equipment is safe or isolated are rejected as invalid.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ..schemas.agents import (
    DiagnosticsResult,
    IncidentNarrative,
    MaintenanceProposal,
    NarrativeInput,
    PrognosticsResult,
    SafetyAssessment,
)
from ..schemas.machine import Machine

SYSTEM_PROMPT = """You are GhostShift's incident writer for an industrial maintenance team.
Rewrite the supplied, already-computed findings into clear operational language.
Rules:
- Use only facts in the input. Do not invent measurements, parts, dates or stock.
- Do not change or reinterpret the risk tier or the recommended response.
- Never state or imply that equipment is safe, isolated, locked out, or cleared for work.
- Keep units exactly as given. Plain ASCII preferred for sms_key_finding.
Return ONLY a JSON object with keys: headline (<=100 chars), summary (<=800 chars),
technician_brief (<=350 chars), sms_key_finding (<=80 chars). No prose outside the JSON."""

FORBIDDEN = re.compile(
    r"\b(safe to (operate|service|work|touch|restart)|has been (isolated|locked out|de-?energi[sz]ed)|"
    r"no (need for )?(lockout|loto|isolation)|lockout (is )?(complete|not required))\b",
    re.IGNORECASE,
)


class InvalidNarrative(ValueError):
    pass


def build_input(machine: Machine, diag: DiagnosticsResult, prog: PrognosticsResult,
                safety: SafetyAssessment, maint: MaintenanceProposal | None) -> NarrativeInput:
    comp_id = prog.affected_component_id
    comp = next((c for c in machine.components if c.id == comp_id), None)
    hyp = diag.hypotheses[0] if diag.hypotheses else None
    findings = [a.description for a in diag.anomalies[:3]]
    top = next((a for a in diag.sensors if diag.anomalies and a.sensor_id == diag.anomalies[0].sensor_id), None)
    if maint and maint.proposed_part:
        findings.append(f"Proposed part {maint.proposed_part.sku}: {maint.proposed_part.description}")
    return NarrativeInput(
        machine_name=machine.display_name,
        machine_id=machine.id,
        component_name=comp.name if comp else "Unassigned component",
        fault_name=hyp.name if hyp else None,
        risk_tier=safety.risk_tier,
        key_findings=findings,
        rul_text=rul_text(prog),
        recommended_response=safety.recommended_response,
        sms_finding=_sms_finding(top) if top else "deviation from baseline detected",
    )


def rul_text(prog: PrognosticsResult) -> str:
    r = prog.rul
    if r is None or not r.supportable:
        return "time to limit not estimated yet"
    if r.value_hours == 0:
        return "danger limit reached"
    upper = f"{r.upper_hours:.0f}" if r.upper_hours is not None else "?"
    return f"about {r.lower_hours:.0f}-{upper} h to the danger limit"


def deterministic(inp: NarrativeInput) -> IncidentNarrative:
    fault = inp.fault_name or "Unclassified deviation"
    short = inp.sms_finding
    return IncidentNarrative(
        headline=f"{fault} on {inp.machine_id}"[:110],
        summary=f"{short}. {inp.rul_text[0].upper()}{inp.rul_text[1:]}. {inp.recommended_response}"[:900],
        technician_brief=(f"{inp.component_name}: {short}. {inp.rul_text[0].upper()}{inp.rul_text[1:]}. "
                          "Confirm on site before taking anything apart.")[:400],
        sms_key_finding=short,
    )


def _sms_finding(a) -> str:
    """Compact ASCII finding, e.g. 'Fan vibration 2.85 mm/s, 1.8x normal, over alert limit'."""
    name = a.sensor_name.split(" (")[0]
    unit = a.unit.replace("°", "deg ").replace("µ", "u")
    ratio = a.current_value / a.baseline.mean if a.baseline.mean else 0
    text = f"{name} {a.current_value:.3g} {unit}, {ratio:.1f}x normal"
    if a.limit_state.value in ("alert", "danger"):
        text += f", over {a.limit_state.value} limit"
    text = text.encode("ascii", "ignore").decode()
    return text if len(text) <= 90 else text[:87] + "..."


def prompt_for(inp: NarrativeInput) -> str:
    return "Findings (JSON):\n" + inp.model_dump_json(indent=2)


def parse(text: str) -> IncidentNarrative:
    """Extract and validate the first JSON object in an LLM reply."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise InvalidNarrative("No JSON object in model output")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise InvalidNarrative(f"Malformed JSON: {exc}") from exc
    try:
        narrative = IncidentNarrative.model_validate(data)
    except ValidationError as exc:
        raise InvalidNarrative(f"Schema validation failed: {exc.errors()[:3]}") from exc
    blob = " ".join(narrative.model_dump().values())
    if FORBIDDEN.search(blob):
        raise InvalidNarrative("Narrative contains a prohibited safety claim")
    return narrative
