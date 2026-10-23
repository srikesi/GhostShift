"""Machine, component and sensor model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .common import Contract, Provenance, Severity


class SensorRole(str, Enum):
    health = "health"  # used to assess component condition
    context = "context"  # operating context (speed, ambient); not a health signal


class LimitDirection(str, Enum):
    above = "above"
    below = "below"


class SensorLimits(Contract):
    direction: LimitDirection = LimitDirection.above
    alert: float | None = None
    danger: float | None = None
    provenance: Provenance


class SensorDefinition(Contract):
    id: str
    name: str
    unit: str
    component_id: str
    role: SensorRole = SensorRole.health
    sample_interval_s: int
    limits: SensorLimits | None = None
    provenance: Provenance


class MaintenanceHistory(Contract):
    last_service_at: datetime
    service_interval_hours: float = Field(gt=0)
    provenance: Provenance


class Component(Contract):
    id: str
    name: str
    type: str
    visualization_id: str = Field(description="Element id in the machine assembly drawing")
    criticality: str = Field(description="high | medium | low")
    maintenance: MaintenanceHistory
    description: str = ""


class OperatingContext(Contract):
    site: str
    line: str
    shift_pattern: str
    duty: str


class Machine(Contract):
    id: str
    display_name: str
    machine_type: str
    model: str
    drawing: str = Field(description="Assembly drawing key used by the frontend")
    context: OperatingContext
    components: list[Component]
    sensors: list[SensorDefinition]
    provenance: Provenance


class HealthBasis(str, Enum):
    sensor = "sensor"
    interval_only = "interval_only"


class ComponentRulEstimate(Contract):
    """Remaining useful life for one component.

    `method` distinguishes a trend-based prediction from a calendar-based
    remaining service interval; they are not interchangeable.
    """

    value_hours: float | None
    lower_hours: float | None = None
    upper_hours: float | None = None
    unit: str = "hours"
    method: str
    supportable: bool
    basis_note: str
    provenance: Provenance


class ComponentHealth(Contract):
    component_id: str
    status: Severity
    health_score: float | None = Field(default=None, ge=0, le=1)
    basis: HealthBasis
    summary: str
    rul: ComponentRulEstimate | None = None
    remaining_service_interval: ComponentRulEstimate


class MachineSummary(Contract):
    id: str
    display_name: str
    machine_type: str
    model: str
    site: str
    line: str
    status: Severity
    status_note: str
    open_incident_id: str | None
    open_incident_tier: str | None = None
    replay_cursor: int
    replay_length: int
