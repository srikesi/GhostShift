"""Dependency wiring: chooses real vs simulated providers from configuration.

This is the single place that maps `Settings` to implementations. To add a new
integration, implement the Protocol in `integrations/base.py`, then select it
here. Tests pass overrides (e.g. a fake LLM) to `build_container`.

Fallback conditions (documented contract):
  demo  - every capability uses its deterministic stub; no network.
  auto  - LLM: Bedrock if GHOSTSHIFT_BEDROCK_MODEL_ID is set, otherwise the template;
          runtime errors / invalid output fall back to the template (labelled).
          SMS / voice: real provider only if selected AND configured, otherwise stub.
          Runtime failures of a configured SMS/voice provider are reported, not masked.
  aws   - selected real providers are used even if misconfigured, so failures are
          visible (provider_failure / failed). No silent fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .agents import DiagnosticsAgent, MaintenanceSupplyAgent, PrognosticsAgent, SafetySupervisor
from .approvals import ApprovalService
from .calendar_service import CalendarService
from .inventory_service import InventoryService
from .config import ExecutionMode, LlmProviderChoice, Settings, SmsProviderChoice, VoiceProviderChoice, get_settings
from .integrations.ai4i import AI4IDatasetAdapter
from .integrations.multimodal_stream import MultimodalStreamAdapter
from .integrations.base import ProviderHealth
from .integrations.bedrock import BedrockConverseLLM
from .integrations.sms import MultiSms, SimulatedSms, TwilioSms
from .integrations.supply import FixturePartsCatalog, SimulatedProcurement, SimulatedWorkOrders
from .integrations.telemetry_fixture import CompositeTelemetryProvider, FixtureTelemetryProvider
from .integrations.voice import ElevenLabsVoice, TextOnlyVoice
from .orchestrator import TEMPLATE_PROVIDER, Orchestrator
from .reference import load_reference_data
from .schemas.workflow import ActionStatus, AutonomyLevel, AutonomySettings
from .state import Store
from .voice_calls import SchedulerCalls, SimulatedCalls, TwilioCalls

log = logging.getLogger("ghostshift")


@dataclass
class Container:
    settings: Settings
    reference: object
    telemetry: CompositeTelemetryProvider
    llm: object | None
    parts: FixturePartsCatalog
    procurement: object
    work_orders: object
    sms: object
    voice: object
    store: Store
    orchestrator: Orchestrator
    approvals: ApprovalService
    inventory: InventoryService
    calendar: CalendarService
    calls: SchedulerCalls

    def provider_health(self, probe: bool = False) -> list[ProviderHealth]:
        out = list(self.telemetry.health())
        if self.llm is not None:
            out.append(self.llm.health(probe=probe))
        else:
            reason = ("demo mode" if self.settings.mode == ExecutionMode.demo else
                      "template selected" if self.settings.llm_provider == LlmProviderChoice.template else
                      "Bedrock not configured; auto mode uses the template")
            out.append(ProviderHealth(capability="llm", provider=TEMPLATE_PROVIDER, configured=True, available=True,
                                      detail=f"Deterministic narrative template ({reason})"))
        out += [self.parts.health(), self.procurement.health(), self.work_orders.health(), self.sms.health(),
                self.voice.health(), self.calls.provider.health()]
        return out

    def reset(self) -> None:
        self.store.reset()
        self.inventory.reset()
        self.calendar.reset()
        self.calls.reset()
        self.orchestrator._screen_cached.cache_clear()


def choose_llm(s: Settings):
    if s.mode == ExecutionMode.demo or s.llm_provider == LlmProviderChoice.template:
        return None
    if s.mode == ExecutionMode.auto and not s.bedrock_configured:
        return None
    return BedrockConverseLLM(model_id=s.bedrock_model_id, region=s.aws_region, timeout_s=s.llm_timeout_s)


def choose_sms(s: Settings):
    if s.mode == ExecutionMode.demo or s.sms_provider != SmsProviderChoice.twilio:
        return SimulatedSms()
    if s.mode == ExecutionMode.auto and not s.twilio_configured:
        return SimulatedSms()
    def twilio(to):
        return TwilioSms(account_sid=s.twilio_account_sid,
                         auth_token=s.twilio_auth_token.get_secret_value() if s.twilio_auth_token else None,
                         from_number=s.twilio_from_number, override_to=to, max_attempts=s.sms_max_attempts)

    primary = twilio(s.demo_technician_phone)
    extras = s.extra_alert_phones
    return MultiSms([primary, *[twilio(p) for p in extras]]) if extras else primary


def choose_calls(s: Settings):
    """Real phone calls only when opted in (a call number and a phone to ring are set); otherwise recorded, not dialled."""
    if s.mode == ExecutionMode.demo or not s.scheduler_call_phone:
        return SimulatedCalls()
    real = TwilioCalls(account_sid=s.twilio_account_sid,
                       auth_token=s.twilio_auth_token.get_secret_value() if s.twilio_auth_token else None,
                       from_number=s.call_from_number)
    if s.mode == ExecutionMode.auto and not real.configured:
        return SimulatedCalls()
    return real


def choose_voice(s: Settings):
    if s.mode == ExecutionMode.demo or s.voice_provider != VoiceProviderChoice.elevenlabs:
        return TextOnlyVoice()
    if s.mode == ExecutionMode.auto and not s.elevenlabs_configured:
        return TextOnlyVoice()
    return ElevenLabsVoice(api_key=s.elevenlabs_api_key.get_secret_value() if s.elevenlabs_api_key else None,
                           voice_id=s.elevenlabs_voice_id, model_id=s.elevenlabs_model_id)


def build_container(settings: Settings | None = None, *, ai4i_path: Path | None = None, enable_multimodal: bool = False, **overrides) -> Container:
    s = settings or get_settings()
    ref = load_reference_data(s.data_dir)
    telemetry = CompositeTelemetryProvider(FixtureTelemetryProvider(ref))
    ai4i_path = ai4i_path or s.ai4i_path
    if ai4i_path:
        adapter = AI4IDatasetAdapter(ai4i_path)
        ref.register_machine(adapter.build_machine(), adapter.build_scenario())
        telemetry.add(adapter.machine_id, adapter)

    if enable_multimodal or getattr(s, "enable_multimodal", False):
        multimodal = MultimodalStreamAdapter()
        for mid in multimodal.machine_ids():
            ref.register_machine(multimodal.build_machine(mid), multimodal.build_scenario(mid))
            telemetry.add(mid, multimodal)

    parts = overrides.get("parts") or FixturePartsCatalog(s.data_dir / "parts_catalog.json")
    llm = overrides["llm"] if "llm" in overrides else choose_llm(s)
    sms = overrides.get("sms") or choose_sms(s)
    voice = overrides.get("voice") or choose_voice(s)
    procurement = overrides.get("procurement") or SimulatedProcurement()
    work_orders = overrides.get("work_orders") or SimulatedWorkOrders()
    store = Store()
    orch = Orchestrator(
        settings=s, reference=ref, telemetry=telemetry, store=store,
        diagnostics=DiagnosticsAgent(ref.fault_modes_for), prognostics=PrognosticsAgent(),
        safety=SafetySupervisor(), maintenance=MaintenanceSupplyAgent(parts, ref.fault_mode, ref.windows_for),
        llm=llm, sms=sms,
    )
    log.info("GhostShift container built: mode=%s llm=%s sms=%s voice=%s", s.mode.value,
             llm.info.name if llm else "template", sms.info.name, voice.info.name)
    store.autonomy = AutonomySettings(level=AutonomyLevel(s.autonomy_level), auto_order_limit_usd=s.auto_order_limit_usd)
    approvals = ApprovalService(store, procurement, work_orders, machine_clock=orch.machine_time)
    orch.approvals = approvals
    inventory = InventoryService(s.data_dir, store, incident_clock=orch.machine_time, site_clock=orch.site_time)
    calendar = CalendarService(s.data_dir, store, ref, incident_clock=orch.machine_time, part_ready=inventory.part_ready_at)
    orch.inventory, orch.calendar = inventory, calendar
    calls = SchedulerCalls(store=store, calendar=calendar, provider=choose_calls(s), phone=s.scheduler_call_phone,
                           public_base_url=s.public_base_url, incident_clock=orch.machine_time)
    orch.calls = calls
    inventory.listeners.append(lambda incident_id: calendar.sync_incident(incident_id))
    if hasattr(parts, "bind_inventory"):
        parts.bind_inventory(inventory)
    if hasattr(procurement, "bind"):
        procurement.bind(inventory)

    def on_decided(act):
        if act.kind.value == "dispatch_work_order" and act.status == ActionStatus.approved:
            calendar.confirm_for_incident(act.incident_id)

    def on_executed(act):
        if act.kind.value == "dispatch_work_order":
            inventory.issue_for_incident(act.incident_id)

    approvals.on_decided, approvals.on_executed = on_decided, on_executed
    return Container(settings=s, reference=ref, telemetry=telemetry, llm=llm, parts=parts, procurement=procurement,
                     work_orders=work_orders, sms=sms, voice=voice, store=store, orchestrator=orch,
                     approvals=approvals, inventory=inventory, calendar=calendar, calls=calls)
