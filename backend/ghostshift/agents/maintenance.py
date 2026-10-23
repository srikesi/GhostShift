"""Maintenance & supply agent: part matching, window proposal and work-order draft."""

from __future__ import annotations

from datetime import timedelta
from typing import Callable

from ..integrations.base import PartsCatalogProvider
from ..schemas.agents import (
    Availability,
    MaintenanceInput,
    MaintenanceProposal,
    MaintenanceWindow,
    PartCandidate,
    RiskTier,
    WorkOrderDraft,
    WorkOrderTask,
)
from ..schemas.common import DataSource, Provenance
from ..schemas.reference import CatalogPart, DowntimeWindow, FaultMode

PRIORITY = {
    RiskTier.critical: "P1 · urgent",
    RiskTier.high: "P2 · next planned window",
    RiskTier.elevated: "P3 · planned",
    RiskTier.routine: "P4 · routine",
}
W_FAULT, W_MODEL, W_AVAIL = 0.55, 0.20, 0.25


class MaintenanceSupplyAgent:
    name = "maintenance_supply"

    def __init__(
        self,
        catalog: PartsCatalogProvider,
        fault_mode: Callable[[str | None], FaultMode | None],
        windows_for: Callable[[str], list[DowntimeWindow]],
    ):
        self._catalog = catalog
        self._fault_mode = fault_mode
        self._windows_for = windows_for

    def run(self, inp: MaintenanceInput) -> MaintenanceProposal:
        comp_id = inp.prognostics.affected_component_id
        if comp_id is None:
            raise ValueError("Maintenance proposal requires an affected component")
        comp = next(c for c in inp.machine.components if c.id == comp_id)
        hyp = inp.diagnostics.hypotheses[0] if inp.diagnostics.hypotheses else None
        fm = self._fault_mode(hyp.fault_mode_id if hyp else None)
        rul = inp.prognostics.rul
        rul_low = rul.lower_hours if rul and rul.supportable else None
        deadline_h = rul_low if rul_low is not None else None
        warnings: list[str] = []

        catalog_prov = Provenance(source=DataSource.fixture, detail=f"Parts catalog ({self._catalog.info.name})")
        ranked = sorted(
            (self._score(p, fm, comp.type, deadline_h, catalog_prov) for p in
             self._catalog.candidates(component_type=comp.type, machine_model=inp.machine.model)),
            key=lambda c: -c.match_score,
        )
        if not ranked:
            warnings.append(f"No catalog part matches component type '{comp.type}' for {inp.machine.model}.")
        part = ranked[0] if ranked else None
        qty = 1

        duration = fm.work_plan.estimated_duration_hours if fm else 4.0
        lead_days = part.availability.lead_time_days if part and part.availability.lead_time_days is not None else 0
        window = self._window(inp, duration, lead_days, rul_low, warnings)

        if fm:
            plan = fm.work_plan
            tasks = [WorkOrderTask(step=i + 1, description=t.description, requires_qualified_person=t.requires_qualified_person)
                     for i, t in enumerate(plan.tasks)]
            title, skills, refs = plan.title, plan.required_skills, plan.safety_references
        else:
            title = f"Inspect {comp.name}"
            tasks = [WorkOrderTask(step=1, description=f"Inspect {comp.name}; confirm the detected deviation.")]
            skills, refs = ["Maintenance technician"], ["Site LOTO procedure (reference only)"]
            warnings.append("No known fault pattern, so the work order is a general inspection.")

        steps = ["Technician verifies the finding on site before any teardown."]
        if inp.safety.required_approvals:
            steps.insert(0, "Maintenance supervisor reviews the requisition and work order (approval required).")
        if part and (part.availability.on_hand or 0) < qty:
            steps.append(f"Confirm lead time for {part.sku} with the supplier.")

        return MaintenanceProposal(
            component_id=comp_id,
            fault_mode_id=fm.id if fm else None,
            proposed_part=part,
            alternatives=ranked[1:3],
            quantity=qty,
            estimated_cost_usd=round(part.unit_cost_usd * qty, 2) if part and part.unit_cost_usd is not None else None,
            maintenance_window=window,
            work_order=WorkOrderDraft(
                title=f"{title} — {inp.machine.id}",
                machine_id=inp.machine.id,
                component_id=comp_id,
                fault_mode_id=fm.id if fm else None,
                priority=PRIORITY[inp.safety.risk_tier],
                tasks=tasks,
                estimated_duration_hours=duration,
                required_skills=skills,
                safety_references=refs,
            ),
            next_steps=steps,
            warnings=warnings,
        )

    def _score(self, p: CatalogPart, fm: FaultMode | None, comp_type: str, deadline_h: float | None,
               prov: Provenance) -> PartCandidate:
        fault = p.fault_modes.get(fm.id, 0.0) if fm else 0.0
        if fault == 0.0 and comp_type in p.component_types:
            fault = 0.3
        avail = p.availability
        in_time = (avail.on_hand or 0) >= p.quantity_per_job or (
            avail.lead_time_days is not None and deadline_h is not None and avail.lead_time_days * 24 <= deadline_h
        )
        rationale = [f"Fits component type '{comp_type}' on {', '.join(p.machine_models)}"]
        if fm and fm.id in p.fault_modes:
            rationale.append(f"Catalog lists it as a remedy for {fm.name} (fit {p.fault_modes[fm.id]:.0%})")
        if (avail.on_hand or 0) > 0:
            rationale.append(f"{avail.on_hand} on hand at {avail.location}")
        elif avail.lead_time_days is not None:
            rationale.append(f"Not stocked; {avail.lead_time_days:g} day lead time"
                             + ("" if in_time else ", later than the RUL lower bound"))
        return PartCandidate(
            sku=p.sku,
            description=p.description,
            manufacturer_part_number=p.manufacturer_part_number,
            unit_cost_usd=p.unit_cost_usd,
            cost_provenance=Provenance(source=DataSource.fixture, detail="Fixture list price; not a vendor quote"),
            match_score=round(W_FAULT * fault + W_MODEL + W_AVAIL * (1.0 if in_time else 0.0), 3),
            match_rationale=rationale,
            availability=Availability(
                on_hand=avail.on_hand, lead_time_days=avail.lead_time_days, location=avail.location,
                provenance=Provenance(source=DataSource.simulated, detail="Simulated availability; not live inventory"),
            ),
        )

    def _window(self, inp: MaintenanceInput, duration_h: float, lead_days: float, rul_low: float | None,
                warnings: list[str]) -> MaintenanceWindow | None:
        ready = inp.as_of + timedelta(days=lead_days)
        prov = Provenance(source=DataSource.fixture, detail="Planned downtime calendar (fixtures/site.json)")
        for w in self._windows_for(inp.machine.id):
            if w.start < ready or (w.end - w.start).total_seconds() / 3600 < duration_h:
                continue
            finish_h = (w.start - inp.as_of).total_seconds() / 3600 + duration_h
            before = None if rul_low is None else finish_h <= rul_low
            if before is False:
                warnings.append("The next planned downtime may be too late. Operations needs to decide on an "
                                "earlier stop.")
            return MaintenanceWindow(
                start=w.start, end=w.end, label=w.label, before_rul_lower_bound=before, provenance=prov,
                rationale=(f"Earliest planned window ≥ part ready time ({ready:%a %d %b %H:%M} UTC) with ≥ {duration_h:g} h"
                           + ("" if rul_low is None else f"; job ends {finish_h:.0f} h from now vs RUL lower bound {rul_low:g} h")),
            )
        warnings.append("No planned downtime fits this job. Operations needs to schedule a stop.")
        return None
