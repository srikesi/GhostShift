"""Loads static machine and site reference data from the fixtures directory."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .schemas.machine import Machine
from .schemas.reference import DowntimeWindow, FaultMode, Scenario, Technician


@dataclass
class ReferenceData:
    machines: dict[str, Machine]
    fault_modes: list[FaultMode]
    scenarios: dict[str, Scenario]
    downtime_windows: list[DowntimeWindow]
    technicians: dict[str, Technician]
    data_dir: Path = field(default=Path("."))

    def machine(self, machine_id: str) -> Machine:
        try:
            return self.machines[machine_id]
        except KeyError:
            raise KeyError(f"Unknown machine '{machine_id}'") from None

    def fault_modes_for(self, machine_type: str) -> list[FaultMode]:
        return [fm for fm in self.fault_modes if fm.machine_type == machine_type]

    def fault_mode(self, fault_mode_id: str | None) -> FaultMode | None:
        return next((fm for fm in self.fault_modes if fm.id == fault_mode_id), None)

    def windows_for(self, machine_id: str) -> list[DowntimeWindow]:
        return sorted((w for w in self.downtime_windows if w.machine_id == machine_id), key=lambda w: w.start)

    def register_machine(self, machine: Machine, scenario: Scenario) -> None:
        """Add a machine at runtime (used by dataset adapters such as AI4I)."""
        self.machines[machine.id] = machine
        self.scenarios[machine.id] = scenario


def load_reference_data(data_dir: Path) -> ReferenceData:
    def read(name: str) -> dict:
        return json.loads((data_dir / name).read_text(encoding="utf-8"))

    machines = {m["id"]: Machine.model_validate(m) for m in read("machines.json")["machines"]}
    fault_modes = [FaultMode.model_validate(fm) for fm in read("fault_modes.json")["fault_modes"]]
    site = read("site.json")
    scenarios = {s["machine_id"]: Scenario.model_validate(s) for s in site["scenarios"]}
    windows = [DowntimeWindow.model_validate(w) for w in site["downtime_windows"]]
    technicians = {t["machine_id"]: Technician.model_validate(t) for t in site["technicians"]}

    for fm in fault_modes:
        owners = [m for m in machines.values() if m.machine_type == fm.machine_type]
        for m in owners:
            if fm.component_id not in {c.id for c in m.components}:
                raise ValueError(f"Fault mode {fm.id} references unknown component {fm.component_id} on {m.id}")
    return ReferenceData(machines, fault_modes, scenarios, windows, technicians, data_dir)
