"""Scheduler calls: GhostShift phones someone, offers repair slots, and books the one they agree to.

The conversation is deterministic code (no model decides anything): it offers the slots the scheduler
already checked against every rule, understands yes / no / a weekday / a time of day, and books the
accepted slot with `CalendarService.reschedule`, so every scheduling rule still applies.

With Autopilot on, an accepted slot is confirmed straight away (the call is the sign-off for the slot).
With Autopilot off it stays a tentative hold until the work order is approved. Physical work is never
released by a call: the lockout/tagout approval stays with a person.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import Callable
from xml.sax.saxutils import escape

import httpx

from .calendar_service import CalendarService, ScheduleError
from .integrations.base import ProviderHealth, info
from .schemas.common import ProviderKind, utcnow
from .schemas.workflow import AutonomyLevel
from .state import Store

try:  # Austin time for what is spoken; fall back to US Central daylight time if tzdata is missing
    from zoneinfo import ZoneInfo

    LOCAL = ZoneInfo("America/Chicago")
except Exception:  # noqa: BLE001
    LOCAL = timezone(timedelta(hours=-5))

DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
        "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 4 + 1, "sun": 6}
YES = ("yes", "yeah", "yep", "yup", "okay", "ok", "sure", "sounds good", "that works", "works for me", "fine", "perfect",
       "great", "go ahead", "book it", "confirm", "i can do that", "let's do it")
NO = ("no", "nope", "not", "can't", "cannot", "doesn't", "does not", "another", "different", "other", "else", "next",
      "later", "earlier", "instead")
END = ("stop", "hang up", "goodbye", "never mind", "cancel", "don't call")
REPEAT = ("repeat", "again", "say that", "what was", "pardon", "sorry")
PARTS = {"morning": range(5, 12), "afternoon": range(12, 17), "evening": range(17, 21), "night": list(range(21, 24)) + list(range(0, 5)),
         "overnight": list(range(21, 24)) + list(range(0, 5))}


@dataclass
class Option:
    start: datetime
    end: datetime
    technician_id: str
    technician_name: str
    window_label: str

    def say(self) -> str:
        s = self.start.astimezone(LOCAL)
        hours = (self.end - self.start).total_seconds() / 3600
        return (f"{s:%A}, {s:%B} {_ordinal(s.day)} at {_clock(s)}, for about {hours:g} hours, with {self.technician_name}")


@dataclass
class CallRecord:
    id: str
    incident_id: str
    to: str
    simulated: bool
    options: list[Option]
    index: int = 0
    status: str = "queued"  # queued | in_progress | completed | failed
    outcome: str | None = None  # accepted | no_slot | declined | hung_up | silent
    accepted: Option | None = None
    confirmed: bool = False
    transcript: list[tuple[str, str]] = field(default_factory=list)
    external_id: str | None = None
    error: str | None = None
    silent_turns: int = 0
    placed_at: datetime = field(default_factory=utcnow)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _clock(t: datetime) -> str:
    h = t.hour % 12 or 12
    return f"{h}{'' if t.minute == 0 else f':{t.minute:02d}'} {'AM' if t.hour < 12 else 'PM'}"


def mask(phone: str) -> str:
    return f"{phone[:2]} ••• ••• ••{phone[-2:]}" if len(phone) > 6 else "••••"


# ----------------------------------------------------------------------- understanding speech
def understand(text: str) -> tuple[str, int | None, str | None]:
    """(intent, weekday, part of day). Intents: end, pick, no, yes, repeat, unknown."""
    t = re.sub(r"[^a-z' ]", " ", text.lower())
    words = set(t.split())
    if any(p in t for p in END):
        return "end", None, None
    day = next((n for w, n in DAYS.items() if w in words), None)
    part = next((p for p in PARTS if p in words), None)
    if day is not None or part is not None:
        return "pick", day, part
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in NO):
        return "no", None, None
    if any(re.search(rf"\b{re.escape(p)}\b", t) for p in YES):
        return "yes", None, None
    if any(p in t for p in REPEAT):
        return "repeat", None, None
    return "unknown", None, None


# -------------------------------------------------------------------------------- providers
class SimulatedCalls:
    """Records the call; nothing is dialled. Drive it with POST /api/voice/calls/{id}/say."""

    info = info("calls-simulated", ProviderKind.stub)
    simulated = True

    def __init__(self):
        self._seq = count(1)

    def place(self, *, to: str, call_id: str, twiml_url: str, status_url: str) -> tuple[str | None, str | None]:
        return f"SIM-CALL-{next(self._seq):05d}", None

    def health(self) -> ProviderHealth:
        return ProviderHealth(capability="calls", provider=self.info, configured=True, available=True,
                              detail="Simulated: calls are recorded, nobody is phoned")


class TwilioCalls:
    """Outbound phone calls through Twilio Programmable Voice (REST, no SDK)."""

    API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    simulated = False

    def __init__(self, *, account_sid: str | None, auth_token: str | None, from_number: str | None,
                 transport: httpx.BaseTransport | None = None):
        self._sid, self._token, self._from, self._transport = account_sid, auth_token, from_number, transport
        self.info = info("twilio-voice", ProviderKind.external)

    @property
    def configured(self) -> bool:
        return bool(self._sid and self._token and self._from)

    def place(self, *, to: str, call_id: str, twiml_url: str, status_url: str) -> tuple[str | None, str | None]:
        if not self.configured:
            return None, "Twilio voice not configured (needs a Twilio phone number that can place calls: GHOSTSHIFT_CALL_FROM_NUMBER)"
        try:
            with httpx.Client(timeout=10.0, transport=self._transport, auth=(self._sid, self._token)) as c:
                r = c.post(self.API.format(sid=self._sid), data={
                    "To": to, "From": self._from, "Url": twiml_url, "Method": "POST",
                    "StatusCallback": status_url, "StatusCallbackMethod": "POST",
                    "StatusCallbackEvent": "completed"})
        except httpx.HTTPError as exc:
            return None, f"Network error: {exc}"
        if r.status_code in (200, 201):
            return r.json().get("sid"), None
        try:
            j = r.json()
            return None, f"Twilio HTTP {r.status_code}: {j.get('code')}: {j.get('message')}"
        except ValueError:
            return None, f"Twilio HTTP {r.status_code}"

    def health(self) -> ProviderHealth:
        detail = "Configured; places calls to GHOSTSHIFT_SCHEDULER_CALL_PHONE only (not probed)" if self.configured else \
            "Missing TWILIO_* credentials or GHOSTSHIFT_CALL_FROM_NUMBER (a Twilio voice number)"
        return ProviderHealth(capability="calls", provider=self.info, configured=self.configured, available=None, detail=detail)


def twilio_signature(token: str, url: str, params: dict[str, str]) -> str:
    """Twilio's request signature: HMAC-SHA1 over the URL plus the sorted form fields."""
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), data.encode(), hashlib.sha1).digest()).decode()


# ---------------------------------------------------------------------------------- service
class SchedulerCalls:
    def __init__(self, *, store: Store, calendar: CalendarService, provider, phone: str | None, public_base_url: str,
                 incident_clock: Callable[[str], datetime | None]):
        self.store, self.calendar, self.provider = store, calendar, provider
        self.phone, self.base = phone, public_base_url.rstrip("/")
        self._clock = incident_clock
        self._calls: dict[str, CallRecord] = {}
        self._seq = count(1)

    def reset(self) -> None:
        with self.store.lock:
            self._calls.clear()

    # --------------------------------------------------------------------- queries
    def calls(self, incident_id: str | None = None) -> list[CallRecord]:
        with self.store.lock:
            return [c for c in self._calls.values() if incident_id in (None, c.incident_id)]

    def get(self, call_id: str) -> CallRecord | None:
        return self._calls.get(call_id)

    # ----------------------------------------------------------------------- start
    def start(self, incident_id: str) -> CallRecord:
        with self.store.lock:
            inc = self.store.incidents.get(incident_id)
            if inc is None or inc.work_order_id is None:
                raise ScheduleError(404, "not_found", "No work order to schedule for this incident")
            if not self.phone:
                raise ScheduleError(409, "no_phone", "Set GHOSTSHIFT_SCHEDULER_CALL_PHONE to the number to call")
            busy = next((c for c in self.calls(incident_id) if c.status in ("queued", "in_progress")), None)
            if busy:
                return busy
            booking = next(iter(self.calendar.bookings(incident_id=incident_id)), None)
            prop = self.calendar.proposal_for_incident(incident_id, exclude=booking.id if booking else None)
            options = self._options(prop, booking)
            if not options:
                raise ScheduleError(409, "no_slot", "No slot fits the rules, so there is nothing to offer. Operations needs to decide.")
            call = CallRecord(id=f"CALL-{next(self._seq):04d}", incident_id=incident_id, to=self.phone,
                              simulated=bool(getattr(self.provider, "simulated", False)), options=options)
            self._calls[call.id] = call
            ext, err = self.provider.place(to=self.phone, call_id=call.id, twiml_url=f"{self.base}/api/voice/calls/{call.id}/twiml",
                                           status_url=f"{self.base}/api/voice/calls/{call.id}/status")
            call.external_id, call.error = ext, err
            if err:
                call.status = "failed"
                self._log(call, "call_failed", f"Could not place the scheduling call: {err}")
            else:
                self._log(call, "call_started", f"Calling {mask(self.phone)} to agree a date for work order {inc.work_order_id}"
                          + (" (simulated)" if call.simulated else ""))
                if call.simulated:
                    call.status = "in_progress"
                    self._say(call, "agent", self.opening(call))
            return call

    @staticmethod
    def _options(prop, booking) -> list[Option]:
        if prop is None:
            return []
        slots = ([prop.chosen] if prop.chosen else []) + [a for a in prop.alternatives if a.feasible]
        return [Option(s.start, s.end, s.technician_id, s.technician_name, s.window_label) for s in slots if s.start]

    def maybe_auto_call(self, incident_id: str) -> CallRecord | None:
        """Autopilot only: one scheduling call per incident, for a held slot at High priority or above."""
        a = self.store.autonomy
        if a is None or a.level != AutonomyLevel.autopilot or not self.phone or self.calls(incident_id):
            return None
        inc = self.store.incidents.get(incident_id)
        booking = next(iter(self.calendar.bookings(incident_id=incident_id)), None)
        if inc is None or booking is None or inc.safety.risk_tier.value not in ("high", "critical"):
            return None
        try:
            return self.start(incident_id)
        except ScheduleError:
            return None

    # ----------------------------------------------------------------- conversation
    def opening(self, call: CallRecord) -> str:
        inc = self.store.incidents[call.incident_id]
        what = inc.maintenance.work_order.title.split(" — ")[0] if inc.maintenance else "a repair"
        o = call.options[0]
        return (f"Hello, this is GhostShift scheduling for Austin D C 2. {inc.machine_id} needs this job: {what.lower()}. "
                f"The earliest safe time is {o.say()}. Does that work for you?")

    def respond(self, call: CallRecord, speech: str) -> tuple[str, bool]:
        """Handle what the person said. Returns what to say next and whether the call is over."""
        with self.store.lock:
            call.status = "in_progress"
            speech = (speech or "").strip()
            if not speech:
                call.silent_turns += 1
                if call.silent_turns >= 2:
                    return self._finish(call, "silent", "I did not hear a reply, so I will leave the slot held and try again later. Goodbye.")
                return self._say(call, "agent", "Sorry, I did not catch that. " + self._offer(call)), False
            call.silent_turns = 0
            call.transcript.append(("caller", speech))
            intent, day, part = understand(speech)
            if intent == "end":
                return self._finish(call, "hung_up", "Okay, no problem. I will leave the held slot as it is. Goodbye.")
            if intent == "yes":
                return self._accept(call, call.options[call.index])
            if intent == "pick":
                found = self._find(call, day, part)
                if found is None:
                    return self._say(call, "agent", "I do not have a checked slot then. " + self._offer(call)), False
                call.index = found
                return self._accept(call, call.options[found]) if self._explicit(speech) else \
                    (self._say(call, "agent", f"I can do {call.options[found].say()}. Does that work?"), False)
            if intent == "no":
                if call.index + 1 >= len(call.options):
                    return self._finish(call, "declined", "Those were all the times that fit our rules. Operations will follow up with you. Goodbye.")
                call.index += 1
                return self._say(call, "agent", f"How about {call.options[call.index].say()}?"), False
            if intent == "repeat":
                return self._say(call, "agent", self._offer(call)), False
            return self._say(call, "agent", "Sorry, I did not understand. Say yes to book it, no for another time, or a day of the week. "
                             + self._offer(call)), False

    @staticmethod
    def _explicit(speech: str) -> bool:
        return bool(re.search(r"\b(book|take|go with|works|let's do|yes|that one)\b", speech.lower()))

    def _offer(self, call: CallRecord) -> str:
        return f"The time on offer is {call.options[call.index].say()}. Does that work?"

    def _find(self, call: CallRecord, day: int | None, part: str | None) -> int | None:
        for i, o in enumerate(call.options):
            s = o.start.astimezone(LOCAL)
            if (day is None or s.weekday() == day) and (part is None or s.hour in PARTS[part]):
                return i
        return None

    def _accept(self, call: CallRecord, o: Option) -> tuple[str, bool]:
        booking = next(iter(self.calendar.bookings(incident_id=call.incident_id)), None)
        try:
            if booking is None:
                self.calendar.sync_incident(call.incident_id)
                booking = next(iter(self.calendar.bookings(incident_id=call.incident_id)), None)
            if booking is not None and (booking.start != o.start or booking.technician_id != o.technician_id):
                self.calendar.reschedule(booking.id, o.start, o.technician_id, actor_name="Scheduling call")
        except ScheduleError as exc:
            reasons = "; ".join((exc.details or {}).get("reasons", [])) or exc.message
            self._log(call, "call_failed", f"The agreed time could not be booked: {reasons}")
            return self._finish(call, "no_slot", "Sorry, that time just stopped fitting the rules. Operations will follow up. Goodbye.")
        call.accepted = o
        autopilot = self.store.autonomy is not None and self.store.autonomy.level == AutonomyLevel.autopilot
        if autopilot and booking is not None:
            self.calendar.confirm(booking.id, by_policy=True)
            call.confirmed = True
            tail = "I have confirmed it in the calendar."
        else:
            tail = "I have held it in the calendar. It is confirmed once the work order is approved."
        self._log(call, "call_accepted", f"{mask(call.to)} agreed {o.say()}. " + (
            "Confirmed by Autopilot." if call.confirmed else "Held until the work order is approved."))
        return self._finish(call, "accepted", f"Great, I have booked {o.say()}. {tail} Thank you. Goodbye.")

    def _finish(self, call: CallRecord, outcome: str, text: str) -> tuple[str, bool]:
        call.outcome, call.status = outcome, "completed"
        if outcome not in ("accepted",):
            self._log(call, "call_ended", f"The scheduling call ended without a booking ({outcome.replace('_', ' ')}).")
        self._say(call, "agent", text)
        return text, True

    def _say(self, call: CallRecord, who: str, text: str) -> str:
        call.transcript.append((who, text))
        return text

    def _log(self, call: CallRecord, kind: str, text: str) -> None:
        actor = "policy" if kind == "call_accepted" and call.confirmed else "ghostshift"
        self.store.log(call.incident_id, actor, "GhostShift", kind, text, self._clock(call.incident_id))

    def mark_status(self, call: CallRecord, twilio_status: str) -> None:
        if twilio_status in ("busy", "no-answer", "failed", "canceled") and call.status != "completed":
            call.status, call.outcome = "failed", twilio_status.replace("-", "_")
            self._log(call, "call_failed", f"The scheduling call was not answered ({twilio_status}).")
        elif twilio_status == "completed" and call.status != "completed":
            call.status, call.outcome = "completed", call.outcome or "hung_up"

    # ------------------------------------------------------------------------ twiml
    @staticmethod
    def gather(url: str, say: str) -> str:
        return (f'<?xml version="1.0" encoding="UTF-8"?><Response>'
                f'<Gather input="speech" action="{escape(url)}" method="POST" speechTimeout="auto" language="en-US">'
                f'<Say voice="Polly.Joanna">{escape(say)}</Say></Gather>'
                f'<Redirect method="POST">{escape(url)}</Redirect></Response>')

    @staticmethod
    def hangup(say: str) -> str:
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Say voice="Polly.Joanna">{escape(say)}</Say><Hangup/></Response>'
