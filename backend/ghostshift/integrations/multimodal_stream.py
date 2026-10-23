"""Multimodal Synthetic Telemetry Provider.

Hardens physical sensor data (AI4I milling telemetry) with high-frequency
acoustic emissions (TwelveLabs/Nova Sonic), infrared thermal hotspots (Nova Vision),
swarf optical discoloration, and 3D coordinate failure anchors for Three.js rendering.

Conforms strictly to the `TelemetryProvider` protocol in `backend/ghostshift/integrations/base.py`.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Literal

from ..schemas.common import DataSource, Provenance, ProviderKind, Severity
from ..schemas.machine import (
    Component,
    Machine,
    MaintenanceHistory,
    OperatingContext,
    SensorDefinition,
    SensorLimits,
    SensorRole,
)
from ..schemas.reference import Scenario, ScenarioPhaseDef
from ..schemas.telemetry import Anchor3D, MultimodalTick, TelemetryPoint, TelemetryWindow
from .base import ProviderHealth, info

_START_TIME = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)

MULTIMODAL_SENSORS = [
    # Physical / AI4I sensors
    ("rotational_speed", "Spindle Speed", "rpm", "spindle_drive", SensorRole.context, 1000.0, 1800.0),
    ("torque", "Spindle Torque", "N·m", "spindle_drive", SensorRole.health, 60.0, 70.0),
    ("air_temp", "Ambient Air Temp", "°C", "thermal_system", SensorRole.context, 30.0, 35.0),
    ("process_temp", "Process Temperature", "°C", "thermal_system", SensorRole.health, 40.0, 43.0),
    ("tool_wear", "Accumulated Tool Wear", "min", "cutting_tool", SensorRole.health, 200.0, 240.0),
    # Multimodal enhancements
    ("acoustic_db", "Acoustic Emissions", "dB", "acoustic_sensor", SensorRole.health, 80.0, 90.0),
    ("acoustic_frequency_hz", "Dominant Acoustic Frequency", "Hz", "acoustic_sensor", SensorRole.health, 2000.0, 3000.0),
    ("thermal_max_c", "IR Thermal Hotspot Peak", "°C", "thermal_camera", SensorRole.health, 65.0, 85.0),
    ("swarf_discoloration", "Swarf Chip Discoloration", "ratio", "optical_sensor", SensorRole.health, 0.20, 0.35),
]


class MultimodalStreamAdapter:
    """Simulates real-time multimodal sensor telemetry with 3D coordinate anchors."""

    info = info("multimodal-synthetic-stream", ProviderKind.stub)

    def __init__(self, sample_interval_s: int = 1, total_ticks: int = 240):
        self.sample_interval_s = sample_interval_s
        self.total_ticks = total_ticks
        self._machine_ids = ["VMC-07-MULTIMODAL", "AI4I-MULTIMODAL"]
        self._cache: dict[str, list[TelemetryPoint]] = {}

    def _generate_tick(self, index: int) -> MultimodalTick:
        idx = index % self.total_ticks
        t = _START_TIME + timedelta(seconds=index * self.sample_interval_s)

        # 4 distinct failure phases
        if idx < 80:
            # Phase 1: Nominal baseline
            phase = "nominal"
            severity = Severity.normal
            noise = math.sin(idx * 0.2) * 1.5
            rpm = round(1500.0 + noise, 1)
            torque = round(42.0 + math.cos(idx * 0.15) * 1.2, 1)
            air_t = round(21.2 + math.sin(idx * 0.05) * 0.3, 1)
            proc_t = round(31.5 + math.sin(idx * 0.1) * 0.5, 1)
            wear = round(float(idx) * 0.5, 1)
            acoustic_db = round(63.2 + math.sin(idx * 0.3) * 1.1, 1)
            acoustic_hz = round(450.0 + math.sin(idx * 0.4) * 15.0, 1)
            thermal_max = round(38.5 + math.sin(idx * 0.1) * 0.8, 1)
            swarf_disc = round(0.02 + abs(math.sin(idx * 0.05)) * 0.01, 3)
            anchor = Anchor3D(x=0.0, y=100.0, z=250.0, component="Spindle Centerline")

        elif idx < 140:
            # Phase 2: Incipient Bearing Chatter (Warning)
            phase = "incipient_chatter"
            severity = Severity.warning
            step = float(idx - 80)
            rpm = round(1485.0 - step * 0.3 + math.sin(idx * 0.8) * 8.0, 1)
            torque = round(44.0 + step * 0.15 + math.sin(idx * 0.5) * 2.5, 1)
            air_t = round(21.6 + step * 0.01, 1)
            proc_t = round(33.0 + step * 0.08, 1)
            wear = round(40.0 + step * 0.6, 1)
            acoustic_db = round(68.0 + (step / 60.0) * 14.5 + math.sin(idx * 1.2) * 2.0, 1)
            acoustic_hz = round(600.0 + step * 25.0 + math.sin(idx * 0.9) * 50.0, 1)
            thermal_max = round(42.0 + (step / 60.0) * 14.0, 1)
            swarf_disc = round(0.04 + (step / 60.0) * 0.06, 3)
            anchor = Anchor3D(x=120.5, y=45.2, z=310.0, component="Spindle Bearing B")

        elif idx < 200:
            # Phase 3: Critical Thermal Breakdown / Overheating (Critical)
            phase = "critical_heating"
            severity = Severity.critical
            step = float(idx - 140)
            rpm = round(1420.0 - step * 0.8 + math.sin(idx * 1.5) * 15.0, 1)
            torque = round(56.0 + step * 0.22 + math.sin(idx * 0.7) * 3.5, 1)
            air_t = round(22.5 + step * 0.02, 1)
            proc_t = round(39.0 + (step / 60.0) * 6.5, 1)
            wear = round(76.0 + step * 1.2, 1)
            acoustic_db = round(84.0 + (step / 60.0) * 11.0 + math.sin(idx * 2.0) * 2.5, 1)
            acoustic_hz = round(2100.0 + step * 18.0, 1)
            thermal_max = round(58.0 + (step / 60.0) * 30.5, 1)
            swarf_disc = round(0.12 + (step / 60.0) * 0.32, 3)
            anchor = Anchor3D(x=120.5, y=45.2, z=310.0, component="Spindle Bearing B")

        else:
            # Phase 4: Extreme Tool Wear Stall Risk (Critical)
            phase = "tool_wear_stall"
            severity = Severity.critical
            step = float(idx - 200)
            rpm = round(1320.0 - step * 3.5 + math.sin(idx * 2.5) * 25.0, 1)
            torque = round(69.0 + step * 0.2 + math.sin(idx * 1.1) * 4.0, 1)
            air_t = round(23.7 + step * 0.01, 1)
            proc_t = round(45.5 + step * 0.05, 1)
            wear = round(202.0 + step * 1.0, 1)
            acoustic_db = round(94.5 + math.sin(idx * 3.0) * 1.8, 1)
            acoustic_hz = round(3200.0 + math.sin(idx * 1.5) * 120.0, 1)
            thermal_max = round(88.0 + (step / 40.0) * 3.5, 1)
            swarf_disc = round(0.44 + (step / 40.0) * 0.05, 3)
            anchor = Anchor3D(x=0.0, y=0.0, z=150.0, component="Cutting Tool Holder")

        values: dict[str, float | None] = {
            "rotational_speed": rpm,
            "torque": torque,
            "air_temp": air_t,
            "process_temp": proc_t,
            "tool_wear": wear,
            "acoustic_db": acoustic_db,
            "acoustic_frequency_hz": acoustic_hz,
            "thermal_max_c": thermal_max,
            "swarf_discoloration": swarf_disc,
        }

        return MultimodalTick(
            index=index,
            timestamp=t,
            values=values,
            anchor_3d=anchor,
            phase=phase,
            severity=severity,
        )

    def _get_points(self, machine_id: str) -> list[TelemetryPoint]:
        if machine_id not in self._cache:
            points = []
            for i in range(self.total_ticks):
                tick = self._generate_tick(i)
                points.append(
                    TelemetryPoint(index=tick.index, timestamp=tick.timestamp, values=tick.values)
                )
            self._cache[machine_id] = points
        return self._cache[machine_id]

    # TelemetryProvider implementation --------------------------------------
    def machine_ids(self) -> list[str]:
        return list(self._machine_ids)

    def length(self, machine_id: str) -> int:
        return self.total_ticks

    def window(self, machine_id: str, start: int, end: int) -> TelemetryWindow:
        pts = [p for p in self._get_points(machine_id) if start <= p.index <= end]
        prov = Provenance(
            source=DataSource.simulated,
            detail="Synthesized multimodal telemetry (TwelveLabs acoustic, Nova Vision IR, AI4I physics)",
        )
        return TelemetryWindow(
            machine_id=machine_id,
            sensor_ids=[sid for sid, _, _, _, _, _, _ in MULTIMODAL_SENSORS],
            points=pts,
            provenance=prov,
            timestamp_provenance=Provenance(
                source=DataSource.simulated, detail=f"Fixed {self.sample_interval_s}s streaming step"
            ),
            unavailable_fields=[],
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            capability="telemetry",
            provider=self.info,
            configured=True,
            available=True,
            detail="Synthesized real-time multimodal stream active (Acoustic + Thermal Vision + 3D Anchors)",
        )

    # Real-time streaming API -----------------------------------------------
    def stream_tick(self, machine_id: str, cursor: int) -> MultimodalTick:
        return self._generate_tick(cursor)

    # Machine / Reference registration --------------------------------------
    def build_machine(self, machine_id: str = "VMC-07-MULTIMODAL") -> Machine:
        fx = Provenance(source=DataSource.fixture, detail="Multimodal Stream Adapter defaults")
        hist = MaintenanceHistory(last_service_at=_START_TIME, service_interval_hours=1500, provenance=fx)

        components = [
            Component(id="spindle_drive", name="Spindle drive motor & inverter", type="spindle_drive",
                      visualization_id="spindle-drive", criticality="high", maintenance=hist),
            Component(id="spindle_bearing", name="Spindle Bearing B (Rear ceramic)", type="bearing",
                      visualization_id="spindle-bearing-b", criticality="critical", maintenance=hist),
            Component(id="cutting_tool", name="Carbide End Mill Holder", type="cutting_tool",
                      visualization_id="tool-holder", criticality="medium", maintenance=hist),
            Component(id="thermal_system", name="Spindle Chiller & Coolant Jet", type="thermal",
                      visualization_id="chiller-loop", criticality="medium", maintenance=hist),
            Component(id="acoustic_sensor", name="High-frequency Acoustic Sensor", type="sensor",
                      visualization_id="audio-mic", criticality="low", maintenance=hist),
            Component(id="thermal_camera", name="Nova Vision LWIR Infrared Camera", type="camera",
                      visualization_id="flir-camera", criticality="low", maintenance=hist),
            Component(id="optical_sensor", name="Optical Swarf Inspection Camera", type="camera",
                      visualization_id="swarf-cam", criticality="low", maintenance=hist),
        ]

        sensors = [
            SensorDefinition(
                id=sid,
                name=sname,
                unit=unit,
                component_id=comp_id,
                role=role,
                sample_interval_s=self.sample_interval_s,
                limits=SensorLimits(alert=alert, danger=danger, provenance=fx),
                provenance=Provenance(source=DataSource.simulated, detail="Multimodal stream synthetic sensor"),
            )
            for sid, sname, unit, comp_id, role, alert, danger in MULTIMODAL_SENSORS
        ]

        return Machine(
            id=machine_id,
            display_name=f"{machine_id} Cyber-Physical Multimodal Cell",
            machine_type="vertical_machining_center",
            model="Okuma Genos M560-V (Multimodal Guardian Instrumented)",
            drawing="vmc_5axis",
            context=OperatingContext(
                site="Austin Semiconductor Line 4", line="Precision Machining Bay C", shift_pattern="Lone Graveyard Shift", duty="Titanium / Inconel 718"
            ),
            components=components,
            sensors=sensors,
            provenance=fx,
        )

    def build_scenario(self, machine_id: str = "VMC-07-MULTIMODAL") -> Scenario:
        return Scenario(
            machine_id=machine_id,
            telemetry_file="multimodal_synthetic_stream",
            baseline_start_index=0,
            baseline_end_index=79,
            initial_cursor=75,
            jump_cursor=145,
            phases=[
                ScenarioPhaseDef(label="Nominal Baseline", start_index=0, end_index=79),
                ScenarioPhaseDef(label="Incipient Bearing Chatter", start_index=80, end_index=139),
                ScenarioPhaseDef(label="Critical Thermal Breakdown", start_index=140, end_index=199),
                ScenarioPhaseDef(label="Tool Wear Emergency Stall", start_index=200, end_index=239),
            ],
        )
