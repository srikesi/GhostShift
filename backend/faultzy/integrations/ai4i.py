"""Adapter for the AI4I 2020 Predictive Maintenance dataset (UCI, CC BY 4.0).

The dataset is not bundled. Download `ai4i2020.csv` and set
`FAULTZY_AI4I_PATH=/path/to/ai4i2020.csv` to register it as machine `AI4I-MILL`.

What the dataset can and cannot support:
- It has air/process temperature, rotational speed, torque and tool wear.
- It has NO vibration, bearing temperature, motor current or timestamps.
  Timestamps are synthesized at a fixed interval and labelled as such.
- Failure labels (TWF, HDF, PWF, OSF, RNF) are ground truth; they are exposed via
  `labels()` for evaluation only and never fed to the diagnostics agent.
- Rows are independent process snapshots, not a run-to-failure trajectory, so
  trend-based RUL is generally not supportable; prognostics will say so.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..schemas.common import DataSource, Provenance, ProviderKind
from ..schemas.machine import (
    Component,
    MaintenanceHistory,
    Machine,
    OperatingContext,
    SensorDefinition,
    SensorLimits,
    SensorRole,
)
from ..schemas.reference import Scenario, ScenarioPhaseDef
from ..schemas.telemetry import TelemetryPoint, TelemetryWindow
from .base import ProviderHealth, info

# AI4I column -> (normalized sensor id, unit, converter)
COLUMN_MAP: dict[str, tuple[str, str, callable]] = {
    "Air temperature [K]": ("air_temp", "°C", lambda v: v - 273.15),
    "Process temperature [K]": ("process_temp", "°C", lambda v: v - 273.15),
    "Rotational speed [rpm]": ("rotational_speed", "rpm", float),
    "Torque [Nm]": ("torque", "N·m", float),
    "Tool wear [min]": ("tool_wear", "min", float),
}
LABEL_COLUMNS = ["Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF"]
UNAVAILABLE = [
    "vibration (not in dataset)",
    "bearing temperature (not in dataset)",
    "motor current (not in dataset)",
    "timestamps (synthesized at fixed interval)",
]
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


class AI4IDatasetAdapter:
    info = info("ai4i-2020-csv", ProviderKind.stub)

    def __init__(self, path: Path, *, machine_id: str = "AI4I-MILL", sample_interval_s: int = 60, max_rows: int | None = 2000):
        self.path = Path(path)
        self.machine_id = machine_id
        self.sample_interval_s = sample_interval_s
        self.max_rows = max_rows
        self._points: list[TelemetryPoint] | None = None
        self._labels: list[dict[str, int]] | None = None

    def _load(self) -> None:
        if self._points is not None:
            return
        points, labels = [], []
        with self.path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in COLUMN_MAP if c not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"Not an AI4I 2020 file; missing columns: {missing}")
            for i, row in enumerate(reader):
                if self.max_rows is not None and i >= self.max_rows:
                    break
                values = {}
                for col, (sid, _unit, conv) in COLUMN_MAP.items():
                    raw = (row.get(col) or "").strip()
                    values[sid] = round(conv(float(raw)), 3) if raw else None
                points.append(
                    TelemetryPoint(index=i, timestamp=_EPOCH + timedelta(seconds=i * self.sample_interval_s), values=values)
                )
                labels.append({c: int(row.get(c) or 0) for c in LABEL_COLUMNS if c in row})
        self._points, self._labels = points, labels

    # TelemetryProvider ---------------------------------------------------
    def machine_ids(self) -> list[str]:
        return [self.machine_id]

    def length(self, machine_id: str) -> int:
        self._load()
        return len(self._points)

    def window(self, machine_id: str, start: int, end: int) -> TelemetryWindow:
        self._load()
        return TelemetryWindow(
            machine_id=self.machine_id,
            sensor_ids=[sid for sid, _, _ in COLUMN_MAP.values()],
            points=[p for p in self._points if start <= p.index <= end],
            provenance=Provenance(source=DataSource.measured, detail=f"AI4I 2020 dataset ({self.path.name})"),
            timestamp_provenance=Provenance(
                source=DataSource.simulated, detail=f"Synthesized: row index × {self.sample_interval_s}s"
            ),
            unavailable_fields=UNAVAILABLE,
        )

    def labels(self) -> list[dict[str, int]]:
        """Ground-truth failure labels, for offline evaluation only."""
        self._load()
        return list(self._labels)

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            capability="telemetry",
            provider=self.info,
            configured=self.path.exists(),
            available=self.path.exists(),
            detail=f"AI4I 2020 CSV at {self.path}" if self.path.exists() else f"File not found: {self.path}",
        )

    # Reference data --------------------------------------------------------
    def build_machine(self) -> Machine:
        fx = Provenance(source=DataSource.fixture, detail="faultzy/integrations/ai4i.py adapter defaults")
        hist = MaintenanceHistory(last_service_at=_EPOCH, service_interval_hours=2000, provenance=fx)
        comp = lambda cid, name, typ: Component(  # noqa: E731
            id=cid, name=name, type=typ, visualization_id=f"ai4i-{cid}", criticality="medium", maintenance=hist
        )
        limits = {
            "process_temp": SensorLimits(alert=40.0, danger=42.0, provenance=fx),
            "torque": SensorLimits(alert=60.0, danger=70.0, provenance=fx),
            "tool_wear": SensorLimits(alert=200.0, danger=240.0, provenance=fx),
        }
        component_of = {"air_temp": "thermal", "process_temp": "thermal", "rotational_speed": "spindle_drive",
                        "torque": "spindle_drive", "tool_wear": "cutting_tool"}
        roles = {"air_temp": SensorRole.context, "rotational_speed": SensorRole.context}
        src = Provenance(source=DataSource.measured, detail="AI4I 2020 dataset")
        sensors = [
            SensorDefinition(id=sid, name=col.split(" [")[0], unit=unit, component_id=component_of[sid],
                             role=roles.get(sid, SensorRole.health), sample_interval_s=self.sample_interval_s,
                             limits=limits.get(sid), provenance=src)
            for col, (sid, unit, _) in COLUMN_MAP.items()
        ]
        return Machine(
            id=self.machine_id,
            display_name=f"{self.machine_id} AI4I 2020 milling process",
            machine_type="ai4i_milling",
            model="AI4I 2020 synthetic milling dataset",
            drawing="generic",
            context=OperatingContext(site="Dataset", line="AI4I 2020", shift_pattern="n/a", duty="Mixed product types L/M/H"),
            components=[comp("spindle_drive", "Spindle drive", "spindle_drive"), comp("cutting_tool", "Cutting tool", "cutting_tool"),
                        comp("thermal", "Process thermal system", "thermal")],
            sensors=sensors,
            provenance=Provenance(source=DataSource.fixture, detail="Machine model inferred by AI4I adapter"),
        )

    def build_scenario(self) -> Scenario:
        n = self.length(self.machine_id)
        base_end = max(10, n // 5)
        return Scenario(
            machine_id=self.machine_id, telemetry_file=str(self.path), baseline_start_index=0,
            baseline_end_index=base_end, initial_cursor=min(n - 1, base_end + 10), jump_cursor=n - 1,
            phases=[ScenarioPhaseDef(label="Dataset rows", start_index=0, end_index=n - 1)],
        )
