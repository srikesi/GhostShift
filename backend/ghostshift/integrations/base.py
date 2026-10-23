"""Provider interfaces. Agents and the orchestrator depend only on these.

Each capability has a deterministic stub and (where relevant) a real adapter.
`ghostshift.container` decides which implementation is wired in, based on
`Settings.mode` and per-provider configuration. Constructors must never make
network calls; do I/O lazily inside methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from ..schemas.common import Contract, ProviderInfo, ProviderKind
from ..schemas.reference import CatalogPart
from ..schemas.telemetry import TelemetryWindow


class ProviderError(Exception):
    """A provider call failed. `retryable` marks transient failures."""

    def __init__(self, message: str, *, retryable: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class ProviderNotConfigured(ProviderError):
    pass


class ProviderHealth(Contract):
    capability: str
    provider: ProviderInfo
    configured: bool
    available: bool | None = None  # None = not probed (no network call made)
    detail: str


def info(name: str, kind: ProviderKind, model_id: str | None = None) -> ProviderInfo:
    return ProviderInfo(name=name, kind=kind, real=kind == ProviderKind.external, model_id=model_id)


# --- Telemetry --------------------------------------------------------------


@runtime_checkable
class TelemetryProvider(Protocol):
    info: ProviderInfo

    def machine_ids(self) -> list[str]: ...
    def length(self, machine_id: str) -> int: ...
    def window(self, machine_id: str, start: int, end: int) -> TelemetryWindow:
        """Points with index in [start, end] inclusive."""
        ...

    def health(self) -> ProviderHealth: ...


# --- LLM --------------------------------------------------------------------


@dataclass
class LlmResponse:
    text: str
    model_id: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmProvider(Protocol):
    info: ProviderInfo

    def complete(self, system: str, prompt: str, *, max_tokens: int = 700) -> LlmResponse: ...
    def health(self, probe: bool = False) -> ProviderHealth: ...


# --- Parts / procurement / work orders --------------------------------------


class PartsCatalogProvider(Protocol):
    info: ProviderInfo

    def candidates(self, *, component_type: str, machine_model: str) -> list[CatalogPart]: ...
    def health(self) -> ProviderHealth: ...


@dataclass
class SubmissionResult:
    external_reference: str
    simulated: bool
    note: str
    submitted_at: datetime | None = None


class ProcurementProvider(Protocol):
    info: ProviderInfo

    def submit_requisition(self, *, requisition_id: str, sku: str, quantity: int) -> SubmissionResult: ...
    def health(self) -> ProviderHealth: ...


class WorkOrderProvider(Protocol):
    info: ProviderInfo

    def dispatch(self, *, work_order_id: str, title: str, machine_id: str) -> SubmissionResult: ...
    def health(self) -> ProviderHealth: ...


# --- Notifications ----------------------------------------------------------


@dataclass
class SmsResult:
    delivered: bool  # accepted by the provider (real) or recorded (stub)
    simulated: bool
    attempts: int
    external_id: str | None = None
    error: str | None = None
    skipped: bool = False


@dataclass
class DeliveryStatus:
    """Final state reported by the provider after a send was accepted."""

    state: str  # "pending" | "delivered" | "failed"
    provider_status: str
    error_code: int | None = None
    error: str | None = None


class SmsProvider(Protocol):
    info: ProviderInfo

    def send(self, *, to: str, body: str) -> SmsResult: ...
    def health(self) -> ProviderHealth: ...
    # Optional: providers that can report carrier delivery implement `delivery_status(external_id)`.


@dataclass
class VoiceResult:
    audio: bytes | None
    mime_type: str | None
    simulated: bool
    error: str | None = None
    meta: dict = field(default_factory=dict)


class VoiceProvider(Protocol):
    info: ProviderInfo

    def synthesize(self, text: str) -> VoiceResult: ...
    def health(self) -> ProviderHealth: ...
