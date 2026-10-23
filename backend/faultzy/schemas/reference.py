"""Shapes of static reference fixtures (fault signatures, catalog, site data)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Contract


class SignatureCondition(Contract):
    sensor: str
    direction: Literal["up", "down", "stable"]
    min_z: float | None = None
    max_abs_z: float | None = None

    def describe(self) -> str:
        if self.direction == "stable":
            return f"{self.sensor} stable (|z| < {self.max_abs_z:g})"
        return f"{self.sensor} {self.direction} (z ≥ {self.min_z:g})"


class WorkPlanTask(Contract):
    description: str
    requires_qualified_person: bool = False


class WorkPlan(Contract):
    title: str
    estimated_duration_hours: float
    required_skills: list[str]
    tasks: list[WorkPlanTask]
    safety_references: list[str]


class FaultMode(Contract):
    id: str
    name: str
    machine_type: str
    component_id: str
    required: list[SignatureCondition]
    supporting: list[SignatureCondition] = Field(default_factory=list)
    contra: list[SignatureCondition] = Field(default_factory=list)
    work_plan: WorkPlan


class CatalogAvailability(Contract):
    on_hand: int | None
    lead_time_days: float | None
    location: str | None


class CatalogPart(Contract):
    sku: str
    description: str
    manufacturer_part_number: str
    component_types: list[str]
    machine_models: list[str]
    fault_modes: dict[str, float]
    unit_cost_usd: float | None
    quantity_per_job: int = 1
    availability: CatalogAvailability


class ScenarioPhaseDef(Contract):
    label: str
    start_index: int
    end_index: int


class Scenario(Contract):
    machine_id: str
    telemetry_file: str
    baseline_start_index: int
    baseline_end_index: int
    initial_cursor: int
    jump_cursor: int
    phases: list[ScenarioPhaseDef]


class DowntimeWindow(Contract):
    machine_id: str
    label: str
    start: datetime
    end: datetime


class Technician(Contract):
    machine_id: str
    label: str
    phone: str
