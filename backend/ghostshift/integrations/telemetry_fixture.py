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
        from datetime import datetime, timezone
        from ..schemas.common import Severity
        from ..schemas.telemetry import Anchor3D, MultimodalTick
        pts = provider.window(machine_id, cursor, cursor).points
        pt = pts[0] if pts else None
        return MultimodalTick(
            index=cursor,
            timestamp=pt.timestamp if pt else datetime.now(timezone.utc),
            values=pt.values if pt else {},
            anchor_3d=Anchor3D(x=0.0, y=100.0, z=250.0, component="Spindle Centerline"),
            phase="nominal",
            severity=Severity.normal,
        )

    def provider_info(self, machine_id: str):
        return self._for(machine_id).info

    def health(self) -> list[ProviderHealth]:
        seen, out = set(), []
        for p in [self._default, *self._routes.values()]:
            if id(p) not in seen:
                seen.add(id(p))
                out.append(p.health())
        return out
