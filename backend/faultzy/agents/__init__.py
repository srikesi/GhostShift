"""Bounded, typed agents. Each is a plain class with `run(input) -> result`.

Agents never call the API layer or construct providers; anything external is
injected. All agents here are deterministic and testable without an LLM.
"""

from .diagnostics import DiagnosticsAgent
from .maintenance import MaintenanceSupplyAgent
from .prognostics import PrognosticsAgent
from .safety import SafetyPolicy, SafetySupervisor

__all__ = ["DiagnosticsAgent", "MaintenanceSupplyAgent", "PrognosticsAgent", "SafetyPolicy", "SafetySupervisor"]
