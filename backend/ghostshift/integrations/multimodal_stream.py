"""Multimodal Synthetic Telemetry Provider.

Hardens physical sensor data with high-frequency acoustic emissions (TwelveLabs/Nova Sonic),
infrared thermal hotspots (Nova Vision), optical swarf discoloration, and 3D coordinate
failure anchors for Three.js rendering.

Supports interactive fault injection ("Break Machine") with realistic E-STOP decay physics
(motor current -> 0A, RPM -> 0 rpm, airflow decay, temperature dissipation).
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
    # Physical / AI4I / CRAH sensors
    ("rotational_speed", "Fan / Spindle Speed", "rpm", "spindle_drive", SensorRole.context, 1000.0, 1800.0),
    ("spindle_speed", "Spindle / Fan Speed", "rpm", "spindle_drive", SensorRole.context, 1000.0, 1800.0),
    ("torque", "Motor Torque", "N·m", "spindle_drive", SensorRole.health, 60.0, 70.0),
    ("spindle_motor_current", "Motor Current", "A", "spindle_drive", SensorRole.health, 18.0, 24.0),
    ("spindle_vib_rms", "Vibration RMS", "mm/s", "spindle_bearing", SensorRole.health, 2.8, 4.5),
    ("air_temp", "Ambient Air Temp", "°C", "thermal_system", SensorRole.context, 30.0, 35.0),
    ("process_temp", "Discharge / Process Temp", "°C", "thermal_system", SensorRole.health, 40.0, 43.0),
    ("spindle_bearing_temp", "Bearing Temperature", "°C", "spindle_bearing", SensorRole.health, 55.0, 75.0),
    ("tool_wear", "Accumulated Wear", "min", "cutting_tool", SensorRole.health, 200.0, 240.0),
    # Multimodal enhancements
    ("acoustic_db", "Acoustic Emissions", "dB", "acoustic_sensor", SensorRole.health, 80.0, 90.0),
    ("acoustic_frequency_hz", "Dominant Acoustic Frequency", "Hz", "acoustic_sensor", SensorRole.health, 2000.0, 3000.0),
    ("thermal_max_c", "IR Thermal Hotspot Peak", "°C", "thermal_camera", SensorRole.health, 65.0, 85.0),
    ("swarf_discoloration", "Optical Discoloration Ratio", "ratio", "optical_sensor", SensorRole.health, 0.20, 0.35),
]


class MultimodalStreamAdapter:
    """Simulates real-time multimodal sensor telemetry with 3D coordinate anchors and E-STOP physics."""

    info = info("multimodal-synthetic-stream", ProviderKind.stub)

    def __init__(self, sample_interval_s: int = 1, total_ticks: int = 240):
        self.sample_interval_s = sample_interval_s
        self.total_ticks = total_ticks
        self._machine_ids = [
            "CRAH-07-MULTIMODAL",
            "CH-02-MULTIMODAL",
            "VMC-07-MULTIMODAL",
            "AI4I-MULTIMODAL",
        ]
        self._cache: dict[str, list[TelemetryPoint]] = {}
        # Fault injection state per machine: None | "mild" | "critical" | "estop"
        self._faults: dict[str, dict] = {}

    def inject_fault(self, machine_id: str, fault_type: Literal["mild", "critical"]) -> dict:
        self._faults[machine_id] = {
            "type": fault_type,
            "tick_started": 0,
            "timestamp": datetime.now(timezone.utc),
        }
        return {"status": "injected", "machine_id": machine_id, "fault_type": fault_type}

    def emergency_stop(self, machine_id: str) -> dict:
        self._faults[machine_id] = {
            "type": "estop",
            "tick_started": 0,
            "timestamp": datetime.now(timezone.utc),
        }
        return {"status": "estop_executed", "machine_id": machine_id}

    def reset_fault(self, machine_id: str) -> dict:
        self._faults.pop(machine_id, None)
        return {"status": "nominal_restored", "machine_id": machine_id}

    def _generate_tick(self, index: int, machine_id: str = "CRAH-07-MULTIMODAL") -> MultimodalTick:
        idx = index % self.total_ticks
        t = _START_TIME + timedelta(seconds=index * self.sample_interval_s)

        fault = self._faults.get(machine_id)
        fault_type = fault["type"] if fault else None

        # 1. Active E-STOP State (Power Cut & Inertial Decay)
        if fault_type == "estop":
            dt = float(fault.get("tick_started", 0))
            fault["tick_started"] = dt + 1.0  # advance decay step
            phase = "emergency_shutdown_loto_active"
            severity = Severity.critical
            # Current cuts immediately to 0
            current = 0.0
            # RPM decays rapidly over 3 seconds
            rpm = round(max(0.0, 350.0 * math.exp(-dt * 0.9)), 1)
            vib = round(max(0.04, 0.04 + 0.1 * math.exp(-dt * 0.5)), 3)
            torque = 0.0
            # Thermal decays towards 22C ambient
            thermal_max = round(22.0 + (88.5 - 22.0) * math.exp(-dt * 0.08), 1)
            proc_t = round(22.0 + (46.0 - 22.0) * math.exp(-dt * 0.05), 1)
            air_t = 21.0
            acoustic_db = round(38.0 + 10.0 * math.exp(-dt * 0.8), 1)
            acoustic_hz = 120.0
            swarf_disc = 0.02
            anchor = Anchor3D(x=0.0, y=0.0, z=0.0, component="LOTO Master Lockout Padlock")

        # 2. Injected Critical Breakdown (Pre-trip state)
        elif fault_type == "critical":
            phase = "catastrophic_breakdown"
            severity = Severity.critical
            rpm = round(1310.0 + math.sin(idx * 2.5) * 45.0, 1)
            torque = 78.4
            current = 24.2
            vib = 6.45
            proc_t = 48.5
            air_t = 24.2
            thermal_max = 89.2
            acoustic_db = 96.8
            acoustic_hz = 3450.0
            swarf_disc = 0.48
            anchor = Anchor3D(x=120.5, y=45.2, z=310.0, component="CRAH Fan Motor Shaft Bearing")

        # 3. Injected Mild Anomaly (Incipient Flutter / Warning)
        elif fault_type == "mild":
            phase = "incipient_flutter"
            severity = Severity.warning
            rpm = round(1740.0 + math.sin(idx * 0.9) * 18.0, 1)
            torque = 48.5
            current = 15.8
            vib = 2.95
            proc_t = 36.2
            air_t = 21.8
            thermal_max = 58.5
            acoustic_db = 82.4
            acoustic_hz = 1850.0
            swarf_disc = 0.08
            anchor = Anchor3D(x=120.5, y=45.2, z=310.0, component="CRAH Fan Motor Shaft Bearing")

        # 4. Standard Replay Phases
        elif idx < 80:
            phase = "nominal"
            severity = Severity.normal
            noise = math.sin(idx * 0.2) * 1.5
            rpm = round(1750.0 + noise, 1)
            torque = round(42.0 + math.cos(idx * 0.15) * 1.2, 1)
            current = round(14.2 + math.sin(idx * 0.1) * 0.3, 2)
            vib = round(1.45 + math.sin(idx * 0.2) * 0.1, 3)
            air_t = round(21.2 + math.sin(idx * 0.05) * 0.3, 1)
            proc_t = round(31.5 + math.sin(idx * 0.1) * 0.5, 1)
            thermal_max = round(38.5 + math.sin(idx * 0.1) * 0.8, 1)
            acoustic_db = round(63.2 + math.sin(idx * 0.3) * 1.1, 1)
            acoustic_hz = round(450.0 + math.sin(idx * 0.4) * 15.0, 1)
            swarf_disc = round(0.02 + abs(math.sin(idx * 0.05)) * 0.01, 3)
            anchor = Anchor3D(x=0.0, y=100.0, z=250.0, component="CRAH Supply Air Centerline")

        elif idx < 140:
            phase = "incipient_chatter"
            severity = Severity.warning
            step = float(idx - 80)
            rpm = round(1720.0 - step * 0.5 + math.sin(idx * 0.8) * 8.0, 1)
            torque = round(44.0 + step * 0.15, 1)
            current = round(15.1 + step * 0.02, 2)
            vib = round(1.85 + (step / 60.0) * 1.0, 3)
            air_t = round(21.6 + step * 0.01, 1)
            proc_t = round(33.0 + step * 0.08, 1)
            thermal_max = round(42.0 + (step / 60.0) * 14.0, 1)
            acoustic_db = round(68.0 + (step / 60.0) * 14.5, 1)
            acoustic_hz = round(600.0 + step * 25.0, 1)
            swarf_disc = round(0.04 + (step / 60.0) * 0.06, 3)
            anchor = Anchor3D(x=120.5, y=45.2, z=310.0, component="CRAH Fan Motor Shaft Bearing")

        elif idx < 200:
            phase = "critical_heating"
            severity = Severity.critical
            step = float(idx - 140)
            rpm = round(1640.0 - step * 1.2, 1)
            torque = round(56.0 + step * 0.22, 1)
            current = round(17.8 + step * 0.08, 2)
            vib = round(3.2 + (step / 60.0) * 2.2, 3)
            air_t = round(22.5 + step * 0.02, 1)
            proc_t = round(39.0 + (step / 60.0) * 6.5, 1)
            thermal_max = round(58.0 + (step / 60.0) * 30.5, 1)
            acoustic_db = round(84.0 + (step / 60.0) * 11.0, 1)
            acoustic_hz = round(2100.0 + step * 18.0, 1)
            swarf_disc = round(0.12 + (step / 60.0) * 0.32, 3)
            anchor = Anchor3D(x=120.5, y=45.2, z=310.0, component="CRAH Fan Motor Shaft Bearing")

        else:
            phase = "tool_wear_stall"
            severity = Severity.critical
            step = float(idx - 200)
            rpm = round(1320.0 - step * 3.5, 1)
            torque = round(69.0 + step * 0.2, 1)
            current = round(23.5 + step * 0.02, 2)
            vib = round(5.8 + step * 0.03, 3)
            air_t = round(23.7 + step * 0.01, 1)
            proc_t = round(45.5 + step * 0.05, 1)
            thermal_max = round(88.0 + (step / 40.0) * 3.5, 1)
            acoustic_db = round(94.5, 1)
            acoustic_hz = round(3200.0, 1)
            swarf_disc = round(0.44 + (step / 40.0) * 0.05, 3)
            anchor = Anchor3D(x=0.0, y=0.0, z=150.0, component="CRAH Impeller Runner")

        values: dict[str, float | None] = {
            "rotational_speed": rpm,
            "spindle_speed": rpm,
            "torque": torque,
            "spindle_motor_current": current,
            "spindle_vib_rms": vib,
            "air_temp": air_t,
            "process_temp": proc_t,
            "spindle_bearing_temp": thermal_max,
            "tool_wear": 45.0,
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
                tick = self._generate_tick(i, machine_id=machine_id)
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
            detail="Synthesized multimodal telemetry (TwelveLabs acoustic, Nova Vision IR, CRAH airflow)",
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
            detail="Synthesized real-time multimodal stream active with E-STOP decay physics",
        )

    # Real-time streaming API -----------------------------------------------
    def stream_tick(self, machine_id: str, cursor: int) -> MultimodalTick:
        return self._generate_tick(cursor, machine_id=machine_id)

    # Machine / Reference registration --------------------------------------
    def build_machine(self, machine_id: str = "CRAH-07-MULTIMODAL") -> Machine:
        fx = Provenance(source=DataSource.fixture, detail="Multimodal Stream Adapter defaults")
        hist = MaintenanceHistory(last_service_at=_START_TIME, service_interval_hours=1500, provenance=fx)

        components = [
            Component(id="spindle_drive", name="Fan motor & variable frequency drive", type="fan_motor",
                      visualization_id="crah-fan-motor", criticality="high", maintenance=hist),
            Component(id="spindle_bearing", name="Fan shaft bearing B (Drive end)", type="bearing",
                      visualization_id="crah-fan-bearing", criticality="critical", maintenance=hist),
            Component(id="cutting_tool", name="Chilled water cooling coil", type="cooling_coil",
                      visualization_id="cooling-coil", criticality="medium", maintenance=hist),
            Component(id="thermal_system", name="Air distribution & supply plenum", type="thermal",
                      visualization_id="supply-plenum", criticality="medium", maintenance=hist),
            Component(id="acoustic_sensor", name="High-frequency Acoustic Sensor", type="sensor",
                      visualization_id="audio-mic", criticality="low", maintenance=hist),
            Component(id="thermal_camera", name="Nova Vision LWIR Infrared Camera", type="camera",
                      visualization_id="flir-camera", criticality="low", maintenance=hist),
            Component(id="optical_sensor", name="Optical Belt/Filter Inspection Camera", type="camera",
                      visualization_id="filter-cam", criticality="low", maintenance=hist),
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
            display_name=f"{machine_id} Data Center Cooling Cell",
            machine_type="multimodal_cyber_physical",
            model="Liebert CW CRAH (GhostShift Multimodal Guardian Instrumented)",
            drawing="crah_unit",
            context=OperatingContext(
                site="Austin Data Center Pod 3", line="Row 4 High-Density Cold Aisle", shift_pattern="Lone Graveyard Shift", duty="75 kW / Rack Continuous Heat Load"
            ),
            components=components,
            sensors=sensors,
            provenance=fx,
        )

    def build_scenario(self, machine_id: str = "CRAH-07-MULTIMODAL") -> Scenario:
        return Scenario(
            machine_id=machine_id,
            telemetry_file="multimodal_synthetic_stream",
            baseline_start_index=0,
            baseline_end_index=79,
            initial_cursor=75,
            jump_cursor=145,
            phases=[
                ScenarioPhaseDef(label="Nominal Cold Aisle Baseline", start_index=0, end_index=79),
                ScenarioPhaseDef(label="Incipient Bearing Chatter", start_index=80, end_index=139),
                ScenarioPhaseDef(label="Critical Thermal Breakdown", start_index=140, end_index=199),
                ScenarioPhaseDef(label="Impeller Stall & Outage Risk", start_index=200, end_index=239),
            ],
        )
