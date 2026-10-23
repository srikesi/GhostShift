"""Deterministic telemetry replay from the CSV fixtures (simulated data)."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from ..reference import ReferenceData
from ..schemas.common import DataSource, Provenance, ProviderKind
from ..schemas.telemetry import TelemetryPoint, TelemetryWindow
from .base import ProviderHealth, info


def read_wide_csv(path: Path, sensor_ids: list[str]) -> list[TelemetryPoint]:
    """Read `index,timestamp,<sensor...>` CSV. Empty cells become None (missing)."""
    points: list[TelemetryPoint] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            values: dict[str, float | None] = {}
            for sid in sensor_ids:
                raw = (row.get(sid) or "").strip()
                values[sid] = float(raw) if raw else None
            points.append(
                TelemetryPoint(
                    index=int(row["index"]),
                    timestamp=datetime.fromisoformat(row["timestamp"].replace("Z", "+00:00")),
                    values=values,
                )
            )
    return points


class FixtureTelemetryProvider:
    """Serves simulated telemetry fixtures; the cursor lives in application state."""

    info = info("fixture-replay", ProviderKind.stub)

    def __init__(self, reference: ReferenceData):
        self._ref = reference
        self._machine_ids = [mid for mid in reference.scenarios if mid in reference.machines]
        self._cache: dict[str, list[TelemetryPoint]] = {}

    def _points(self, machine_id: str) -> list[TelemetryPoint]:
        if machine_id not in self._cache:
            scenario = self._ref.scenarios[machine_id]
            machine = self._ref.machine(machine_id)
            path = self._ref.data_dir / scenario.telemetry_file
            self._cache[machine_id] = read_wide_csv(path, [s.id for s in machine.sensors])
        return self._cache[machine_id]

    def machine_ids(self) -> list[str]:
        return list(self._machine_ids)

    def length(self, machine_id: str) -> int:
        return len(self._points(machine_id))

    def window(self, machine_id: str, start: int, end: int) -> TelemetryWindow:
        machine = self._ref.machine(machine_id)
        pts = [p for p in self._points(machine_id) if start <= p.index <= end]
        scenario = self._ref.scenarios[machine_id]
        return TelemetryWindow(
            machine_id=machine_id,
            sensor_ids=[s.id for s in machine.sensors],
            points=pts,
            provenance=Provenance(
                source=DataSource.simulated,
                detail=f"{scenario.telemetry_file} (deterministic simulation, scripts/generate_fixtures.py)",
            ),
            timestamp_provenance=Provenance(source=DataSource.simulated, detail="Fixture timestamps, 15 min interval"),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            capability="telemetry",
            provider=self.info,
            configured=True,
            available=True,
            detail=f"Replaying simulated fixtures for {', '.join(self.machine_ids())}",
        )


class CompositeTelemetryProvider:
    """Routes machine ids to the provider that owns them."""

    def __init__(self, default: FixtureTelemetryProvider):
        self._default = default
        self._routes: dict[str, object] = {}
        self.info = default.info
        self._faults: dict[str, dict] = {}

    def add(self, machine_id: str, provider) -> None:
        self._routes[machine_id] = provider

    def _for(self, machine_id: str):
        return self._routes.get(machine_id, self._default)

    def machine_ids(self) -> list[str]:
        return self._default.machine_ids() + list(self._routes)

    def length(self, machine_id: str) -> int:
        return self._for(machine_id).length(machine_id)

    def window(self, machine_id: str, start: int, end: int) -> TelemetryWindow:
        return self._for(machine_id).window(machine_id, start, end)

    def stream_tick(self, machine_id: str, cursor: int):
        provider = self._for(machine_id)
        if hasattr(provider, "stream_tick"):
            return provider.stream_tick(machine_id, cursor)
        for p in self._routes.values():
            if hasattr(p, "stream_tick"):
                return p.stream_tick(machine_id, cursor)
        from datetime import datetime, timezone
        import math
        from ..schemas.common import Severity
        from ..schemas.telemetry import Anchor3D, MultimodalTick
        pts = provider.window(machine_id, cursor, cursor).points
        pt = pts[0] if pts else None
        vals = dict(pt.values) if pt and pt.values else {}
        phase = "nominal"
        sev = Severity.normal

        fault = self._faults.get(machine_id)
        if fault:
            ftype = fault.get("type")
            dt = float(fault.get("tick_started", 0))
            fault["tick_started"] = dt + 1.0

            if ftype == "estop":
                phase = "emergency_shutdown_loto_active"
                sev = Severity.critical
                vals["fan_motor_current"] = 0.0
                vals["compressor_motor_current"] = 0.0
                vals["spindle_motor_current"] = 0.0
                # Realistic mechanical rotor coast-down curve from ~1460 RPM over 7-8 seconds
                # dt advances every tick (0.5s at 2.0x stream speed)
                decay_rpm = 1460.0 * math.exp(-dt * 0.45)
                vals["fan_speed"] = round(decay_rpm if decay_rpm >= 15.0 else 0.0, 1)
                vals["spindle_speed"] = vals["fan_speed"]
                vals["rotational_speed"] = vals["fan_speed"]
                vals["fan_vibration"] = round(max(0.04, 0.04 + 0.3 * math.exp(-dt * 0.3)), 3)
                vals["fan_bearing_temp"] = round(22.0 + (vals.get("fan_bearing_temp", 45.0) - 22.0) * math.exp(-dt * 0.05), 1)
                vals["discharge_temp"] = vals["fan_bearing_temp"]
                vals["acoustic_db"] = round(38.0 + (vals.get("acoustic_db", 65.0) - 38.0) * math.exp(-dt * 0.4), 1)

            elif ftype == "critical":
                phase = "catastrophic_breakdown"
                sev = Severity.critical
                # Live dynamic oscillations: erratic bearing binding, current spikes, thermal runaway
                rpm_jitter = math.sin(dt * 1.8) * 45.0 + math.cos(dt * 3.4) * 22.0
                vals["fan_speed"] = round(1310.0 + rpm_jitter, 1)
                vals["spindle_speed"] = vals["fan_speed"]
                vals["rotational_speed"] = vals["fan_speed"]
                
                current_surge = math.sin(dt * 2.2) * 2.8 + (math.sin(dt * 0.7) * 1.2)
                vals["fan_motor_current"] = round(24.5 + current_surge, 2)
                vals["compressor_motor_current"] = round(185.0 + current_surge * 4.0, 1)
                vals["spindle_motor_current"] = vals["fan_motor_current"]
                
                vib_flutter = math.sin(dt * 2.5) * 0.85 + math.cos(dt * 4.1) * 0.45
                vals["fan_vibration"] = round(6.45 + vib_flutter, 3)
                
                # Upward thermal runaway creep
                temp_creep = min(12.0, dt * 0.45) + (math.sin(dt * 0.9) * 0.8)
                vals["fan_bearing_temp"] = round(88.0 + temp_creep, 1)
                vals["discharge_temp"] = round(95.0 + temp_creep, 1)
                
                acoustic_screech = math.sin(dt * 3.1) * 3.5 + math.cos(dt * 1.4) * 2.0
                vals["acoustic_db"] = round(96.0 + acoustic_screech, 1)

            elif ftype == "mild":
                phase = "incipient_flutter"
                sev = Severity.warning
                # Live dynamic flutter oscillations
                rpm_flutter = math.sin(dt * 1.2) * 16.0 + math.cos(dt * 2.1) * 8.0
                vals["fan_speed"] = round(1450.0 + rpm_flutter, 1)
                vals["spindle_speed"] = vals["fan_speed"]
                vals["rotational_speed"] = vals["fan_speed"]
                
                vib_wobble = math.sin(dt * 1.7) * 0.45 + math.sin(dt * 3.3) * 0.25
                vals["fan_vibration"] = round(3.85 + vib_wobble, 3)
                
                current_wobble = math.sin(dt * 1.1) * 0.65
                vals["fan_motor_current"] = round(15.4 + current_wobble, 2)
                vals["spindle_motor_current"] = vals["fan_motor_current"]
                
                temp_warmup = min(6.0, dt * 0.25) + (math.sin(dt * 0.5) * 0.4)
                vals["fan_bearing_temp"] = round(51.0 + temp_warmup, 1)
                vals["discharge_temp"] = round(54.0 + temp_warmup, 1)
                
                noise_chatter = math.sin(dt * 2.0) * 2.2 + math.cos(dt * 1.5) * 1.2
                vals["acoustic_db"] = round(82.0 + noise_chatter, 1)

            elif ftype == "spinup":
                phase = "soft_start_spinup"
                sev = Severity.normal
                target_rpm = vals.get("fan_speed", 1460.0) or 1460.0
                target_current = vals.get("fan_motor_current", 14.2) or 14.2
                # Asymptotic soft-start ramp: 1 - exp(-dt * 0.4)
                # Starts at ~200 rpm on tick 0, rises smoothly to 98% nominal over 8-10 ticks (~4-5 sec)
                progress = 1.0 - math.exp(-dt * 0.35)
                vals["fan_speed"] = round(target_rpm * progress, 1)
                vals["spindle_speed"] = vals["fan_speed"]
                vals["rotational_speed"] = vals["fan_speed"]
                # Inrush current profile: inrush surge at start (~18A) stabilizing to nominal 14.2A
                inrush = 4.0 * math.exp(-dt * 0.4)
                vals["fan_motor_current"] = round((target_current * progress) + inrush, 2)
                vals["fan_vibration"] = round(0.4 + (1.1 * progress), 2)
                vals["acoustic_db"] = round(42.0 + (22.0 * progress), 1)

                # Once within 98% of target, release to normal baseline
                if progress >= 0.96 or dt >= 12.0:
                    self._faults.pop(machine_id, None)

        return MultimodalTick(
            index=cursor,
            timestamp=pt.timestamp if pt else datetime.now(timezone.utc),
            values=vals,
            anchor_3d=Anchor3D(x=0.0, y=100.0, z=250.0, component="CRAH Air Handler Centerline" if "CRAH" in machine_id else "Mainframe Rack Fan Centerline"),
            phase=phase,
            severity=sev,
        )

    def inject_fault(self, machine_id: str, fault_type: str) -> dict:
        self._faults[machine_id] = {"type": fault_type, "tick_started": 0}
        provider = self._for(machine_id)
        if hasattr(provider, "inject_fault"):
            provider.inject_fault(machine_id, fault_type)
        for p in self._routes.values():
            if hasattr(p, "inject_fault"):
                p.inject_fault(machine_id, fault_type)
        return {"status": "injected", "machine_id": machine_id, "fault_type": fault_type}

    def emergency_stop(self, machine_id: str) -> dict:
        self._faults[machine_id] = {"type": "estop", "tick_started": 0}
        provider = self._for(machine_id)
        if hasattr(provider, "emergency_stop"):
            provider.emergency_stop(machine_id)
        for p in self._routes.values():
            if hasattr(p, "emergency_stop"):
                p.emergency_stop(machine_id)
        return {"status": "estop_executed", "machine_id": machine_id}

    def reset_fault(self, machine_id: str) -> dict:
        # Initiate realistic soft-start motor spin-up ramp
        self._faults[machine_id] = {"type": "spinup", "tick_started": 0}
        provider = self._for(machine_id)
        if hasattr(provider, "reset_fault"):
            provider.reset_fault(machine_id)
        for p in self._routes.values():
            if hasattr(p, "reset_fault"):
                p.reset_fault(machine_id)
        return {"status": "spinup_initiated", "machine_id": machine_id}

    def provider_info(self, machine_id: str):
        return self._for(machine_id).info

    def health(self) -> list[ProviderHealth]:
        seen, out = set(), []
        for p in [self._default, *self._routes.values()]:
            if id(p) not in seen:
                seen.add(id(p))
                out.append(p.health())
        return out
