"""Normalized telemetry. Agents consume these types, never raw dataset rows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import Contract, Provenance, Severity


class TelemetryPoint(Contract):
    index: int
    timestamp: datetime
    values: dict[str, float | None] = Field(description="sensor_id -> raw value (None = missing)")


class TelemetryWindow(Contract):
    machine_id: str
    sensor_ids: list[str]
    points: list[TelemetryPoint]
    provenance: Provenance
    timestamp_provenance: Provenance
    unavailable_fields: list[str] = Field(
        default_factory=list, description="Fields the source cannot provide for this machine"
    )


class ScenarioPhase(Contract):
    """Ground-truth phase label from the simulation. Never used by diagnostics."""

    label: str
    start_index: int
    end_index: int
    provenance: Provenance


class SeveritySegment(Contract):
    start_index: int
    end_index: int
    severity: Severity


class TelemetryResponse(Contract):
    machine_id: str
    cursor: int
    length: int
    baseline_start_index: int
    baseline_end_index: int
    window: TelemetryWindow
    scenario_phases: list[ScenarioPhase]
    detection_segments: list[SeveritySegment] = Field(
        description="GhostShift screening severity at each replay position up to the cursor (derived)"
    )


class ReplayRequest(Contract):
    action: Literal["reset", "advance", "seek", "to_end"]
    steps: int = Field(default=4, ge=1, le=240)
    cursor: int | None = Field(default=None, ge=0)
    auto_analyze: bool = True


class ReplayResponse(Contract):
    machine_id: str
    cursor: int
    length: int
    screening_severity: Severity
    screening_note: str
    triggered_run_id: str | None = None
    triggered_incident_id: str | None = None



class Anchor3D(Contract):
    """Spatial 3D coordinate anchor for Three.js failure pinpointing."""

    x: float = Field(description="X coordinate in machine frame (mm)")
    y: float = Field(description="Y coordinate in machine frame (mm)")
    z: float = Field(description="Z coordinate in machine frame (mm)")
    component: str = Field(description="Component name target")


class MultimodalTick(Contract):
    """Single tick of high-frequency multimodal telemetry stream."""

    index: int
    timestamp: datetime
    values: dict[str, float | None]
    anchor_3d: Anchor3D
    phase: str
    severity: Severity
