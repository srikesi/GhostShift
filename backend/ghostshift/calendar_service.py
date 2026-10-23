"""Mock calendar and scheduler for maintenance work.

Proposes the best slot for a work order, holds it tentatively when the work order is drafted, and
confirms it only after the work order is approved. All people, shifts and bookings are simulated.

A slot is accepted only when it is: inside a planned maintenance window, after the part has
arrived, finished before the earliest estimated limit, staffed by a free technician with the
required skills on shift, and clear of maintenance on the redundant unit (N+1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .reference import ReferenceData
from .schemas.common import utcnow
from .schemas.ops import (
    Booking,
    BookingStatus,
    CalendarEvent,
    CalendarView,
    FixtureBooking,
    RedundancyRule,
    ScheduleConstraints,
    ScheduleProposal,
    ShiftBlock,
    SlotOption,
    Technician,
)
from .schemas.workflow import ActionStatus
from .state import Store

STEP = timedelta(minutes=30)
ACTIVE = (BookingStatus.tentative, BookingStatus.confirmed)


class ScheduleError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.details = status_code, code, message, details


@dataclass
class _Busy:
    start: datetime
    end: datetime
    label: str


def _fmt(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%a %d %b %H:%M UTC")


def _ceil(t: datetime) -> datetime:
    t = t.astimezone(timezone.utc).replace(second=0, microsecond=0)
    rem = (t.minute % 30)
    return t if rem == 0 and t.second == 0 else t + timedelta(minutes=30 - rem)


class CalendarService:
    def __init__(self, data_dir: Path, store: Store, reference: ReferenceData, *,
                 incident_clock: Callable[[str], datetime | None],
                 part_ready: Callable[[str], datetime | None] | None = None):
        data = json.loads((data_dir / "calendar.json").read_text(encoding="utf-8"))
        self.store, self.ref = store, reference
        self._incident_clock = incident_clock
        self._part_ready = part_ready or (lambda _iid: None)
        self.technicians = [Technician.model_validate(t) for t in data["technicians"]]
        self.fixture_bookings = [FixtureBooking.model_validate(b) for b in data["bookings"]]
        self.redundancy = [RedundancyRule.model_validate(r) for r in data["redundancy"]]
        self._bookings: dict[str, Booking] = {}

    def reset(self) -> None:
        with self.store.lock:
            self._bookings.clear()

    # ---------------------------------------------------------------- queries
    def partner_of(self, machine_id: str) -> str | None:
        return next((r.partner for r in self.redundancy if r.unit == machine_id), None)

    def bookings(self, *, incident_id: str | None = None, include_cancelled: bool = False) -> list[Booking]:
        with self.store.lock:
            return [b for b in self._bookings.values()
                    if (incident_id is None or b.incident_id == incident_id)
                    and (include_cancelled or b.status != BookingStatus.cancelled)]

    def booking(self, booking_id: str) -> Booking:
        b = self._bookings.get(booking_id)
        if b is None:
            raise ScheduleError(404, "not_found", f"Booking '{booking_id}' not found")
        return b

    def shift_blocks(self, start: datetime, end: datetime) -> list[ShiftBlock]:
        out: list[ShiftBlock] = []
        day = (start - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        while day < end:
            for t in self.technicians:
                for sh in t.shifts:
                    if day.weekday() in sh.days:
                        s, e = day + timedelta(hours=sh.start_hour), day + timedelta(hours=sh.end_hour)
                        if e > start and s < end:
                            out.append(ShiftBlock(technician_id=t.id, start=s, end=e))
            day += timedelta(days=1)
        return sorted(out, key=lambda b: (b.technician_id, b.start))

    def view(self, start: datetime, end: datetime, machine_id: str | None = None) -> CalendarView:
        events: list[CalendarEvent] = []
        for w in self.ref.downtime_windows:
            if machine_id in (None, w.machine_id) and w.end > start and w.start < end:
                events.append(CalendarEvent(id=f"WIN-{w.machine_id}-{w.start:%Y%m%d%H}", kind="maintenance_window",
                                            title=w.label, machine_id=w.machine_id, technician_id=None,
                                            start=w.start, end=w.end))
        for fb in self.fixture_bookings:
            if machine_id in (None, fb.machine_id) and fb.end > start and fb.start < end:
                events.append(CalendarEvent(id=fb.id, kind="existing_job", title=fb.title, machine_id=fb.machine_id,
                                            technician_id=fb.technician_id, start=fb.start, end=fb.end))
        for b in self.bookings():
            if machine_id in (None, b.machine_id) and b.end > start and b.start < end:
                events.append(CalendarEvent(
                    id=b.id, kind="ghostshift_booking" if b.status == BookingStatus.confirmed else "ghostshift_hold",
                    title=b.title, machine_id=b.machine_id, technician_id=b.technician_id, start=b.start, end=b.end,
                    status=b.status.value, work_order_id=b.work_order_id))
        events.sort(key=lambda e: (e.start, e.id))
        return CalendarView(start=start, end=end, technicians=self.technicians, events=events,
                            shifts=self.shift_blocks(start, end), redundancy=self.redundancy)

    # ---------------------------------------------------------------- scheduler
    def _busy(self, *, technician_id: str | None = None, machine_id: str | None = None,
              exclude: str | None = None) -> list[_Busy]:
        out = [_Busy(b.start, b.end, b.title) for b in self.fixture_bookings
               if (technician_id and b.technician_id == technician_id) or (machine_id and b.machine_id == machine_id)]
        out += [_Busy(b.start, b.end, b.title) for b in self.bookings()
                if b.id != exclude and ((technician_id and b.technician_id == technician_id)
                                        or (machine_id and b.machine_id == machine_id))]
        return out

    @staticmethod
    def _clash(busy: list[_Busy], start: datetime, end: datetime) -> _Busy | None:
        return next((b for b in busy if b.start < end and start < b.end), None)

    def _on_shift(self, tech: Technician, start: datetime, end: datetime) -> bool:
        return any(b.start <= start and end <= b.end for b in self.shift_blocks(start, end) if b.technician_id == tech.id)

    def check_slot(self, machine_id: str, start: datetime, duration_h: float, skills: list[str], *,
                   technician_id: str | None = None, exclude: str | None = None,
                   deadline: datetime | None = None) -> tuple[Technician | None, list[str], list[str]]:
        """Check one slot. Returns (technician, blocking reasons, notes about technicians skipped)."""
        end = start + timedelta(hours=duration_h)
        reasons: list[str] = []
        if deadline is not None and end > deadline:
            reasons.append(f"Job would end {_fmt(end)}, after the earliest estimated limit ({_fmt(deadline)})")
        clash = self._clash(self._busy(machine_id=machine_id, exclude=exclude), start, end)
        if clash:
            reasons.append(f"{machine_id} already has \"{clash.label}\" booked then")
        partner = self.partner_of(machine_id)
        if partner:
            pc = self._clash(self._busy(machine_id=partner, exclude=exclude), start, end)
            if pc:
                reasons.append(f"N+1: {partner} is in maintenance (\"{pc.label}\", {_fmt(pc.start)} to {_fmt(pc.end)}), "
                               f"so {machine_id} cannot go offline")
        skilled = [t for t in self.technicians if set(skills) <= set(t.skills)]
        pool = [t for t in skilled if technician_id in (None, t.id)]
        notes: list[str] = []
        if not skilled:
            reasons.append("No technician has all the required skills: " + ", ".join(skills))
        chosen: Technician | None = None
        for t in sorted(pool, key=lambda t: (sum(1 for b in self.bookings() if b.technician_id == t.id), t.id)):
            if not self._on_shift(t, start, end):
                notes.append(f"{t.name} is not on shift")
            elif (c := self._clash(self._busy(technician_id=t.id, exclude=exclude), start, end)):
                notes.append(f"{t.name} is booked: {c.label}")
            else:
                chosen = t
                break
        if skilled and chosen is None:
            reasons.append("No free, on-shift technician with the required skills: " + "; ".join(notes))
        return (chosen if not reasons else None), reasons, notes

    def propose(self, *, machine_id: str, duration_h: float, skills: list[str], as_of: datetime,
                part_ready: datetime | None, deadline: datetime | None, exclude: str | None = None) -> ScheduleProposal:
        earliest = _ceil(max(as_of, part_ready or as_of))
        partner = self.partner_of(machine_id)
        constraints = ScheduleConstraints(duration_hours=duration_h, required_skills=skills, part_ready=part_ready,
                                          must_finish_before=deadline, redundant_unit=partner)
        options: list[SlotOption] = []
        for w in self.ref.windows_for(machine_id):
            if w.end <= as_of:
                continue
            opt = SlotOption(window_label=w.label, window_start=w.start, window_end=w.end, feasible=False)
            if (w.end - w.start).total_seconds() / 3600 < duration_h:
                opt.reasons.append(f"The window is only {(w.end - w.start).total_seconds() / 3600:g} h; the job needs {duration_h:g} h")
            elif w.end < earliest + timedelta(hours=duration_h):
                if part_ready and w.end <= part_ready:
                    opt.reasons.append(f"The part does not arrive until {_fmt(part_ready)}, after this window ends")
                else:
                    opt.reasons.append("Not enough of this window is left to finish the job")
            else:
                start = max(_ceil(w.start), earliest)
                first_reasons: list[str] = []
                while start + timedelta(hours=duration_h) <= w.end:
                    tech, reasons, notes = self.check_slot(machine_id, start, duration_h, skills,
                                                           exclude=exclude, deadline=deadline)
                    if tech is not None:
                        opt.start, opt.end = start, start + timedelta(hours=duration_h)
                        opt.technician_id, opt.technician_name, opt.feasible = tech.id, tech.name, True
                        opt.reasons = [f"Fits: {_fmt(opt.start)} to {opt.end:%H:%M}, {tech.name} is free and on shift"]
                        opt.reasons += [f"Skipped: {n}" for n in notes]
                        break
                    for r in reasons:
                        if r not in first_reasons:
                            first_reasons.append(r)
                    if deadline is not None and start + timedelta(hours=duration_h) > deadline:
                        break
                    start += STEP
                if not opt.feasible:
                    opt.reasons = first_reasons[:3] or ["No start time in this window works"]
            options.append(opt)

        chosen = next((o for o in options if o.feasible), None)
        rationale: list[str] = []
        warnings: list[str] = []
        if chosen:
            rationale.append(f"Earliest slot that meets every rule: {chosen.window_label}, "
                             f"{_fmt(chosen.start)} to {chosen.end:%H:%M} with {chosen.technician_name}")
            if part_ready:
                rationale.append(f"After the part arrives ({_fmt(part_ready)})")
            if deadline:
                rationale.append(f"Finishes {(deadline - chosen.end).total_seconds() / 3600:.0f} h before the earliest "
                                 f"estimated limit ({_fmt(deadline)})")
            else:
                warnings.append("There is no time-to-limit estimate for this problem, so the deadline was not checked.")
            if partner:
                rationale.append(f"{partner} has no maintenance then, so it can carry the load (N+1)")
            rationale += [n for n in chosen.reasons[1:]]
        else:
            warnings.append("Nothing fits" + (f" before {_fmt(deadline)}" if deadline else "")
                            + ". Operations needs to decide: approve an unplanned stop"
                            + (f" with {partner} covering" if partner else "")
                            + ", move other work, or wait for the part.")
        return ScheduleProposal(status="fits" if chosen else "no_fit", machine_id=machine_id, chosen=chosen,
                                rationale=rationale, alternatives=[o for o in options if o is not chosen],
                                warnings=warnings, constraints=constraints)

    # ------------------------------------------------------- work-order driven
    def proposal_for_incident(self, incident_id: str, *, as_of: datetime | None = None,
                              exclude: str | None = None) -> ScheduleProposal | None:
        inc = self.store.incidents.get(incident_id)
        if inc is None or inc.maintenance is None or inc.work_order_id is None:
            return None
        as_of = as_of or self._incident_clock(incident_id) or utcnow()
        m = inc.maintenance
        rul = inc.prognostics.rul
        deadline = as_of + timedelta(hours=rul.lower_hours) if rul and rul.supportable and rul.lower_hours is not None else None
        part_ready = self._part_ready(incident_id)
        if part_ready is None and m.proposed_part and (m.proposed_part.availability.on_hand or 0) < m.quantity:
            lead = m.proposed_part.availability.lead_time_days
            part_ready = as_of + timedelta(days=lead) if lead else None
        return self.propose(machine_id=inc.machine_id, duration_h=m.work_order.estimated_duration_hours,
                            skills=m.work_order.required_skills, as_of=as_of, part_ready=part_ready,
                            deadline=deadline, exclude=exclude)

    def sync_incident(self, incident_id: str) -> Booking | None:
        """Create or refresh the tentative hold for an incident's work order. Never touches confirmed bookings."""
        with self.store.lock:
            inc = self.store.incidents.get(incident_id)
            if inc is None or inc.work_order_id is None:
                return None
            current = next((b for b in self.bookings(incident_id=incident_id)), None)
            if current is not None and current.status == BookingStatus.confirmed:
                return current
            as_of = self._incident_clock(incident_id) or utcnow()
            prop = self.proposal_for_incident(incident_id, as_of=as_of, exclude=current.id if current else None)
            if prop is None:
                return current
            wo = self.store.work_orders[inc.work_order_id]
            log = lambda kind, text: self.store.log(incident_id, "ghostshift", "GhostShift", kind, text, as_of)  # noqa: E731
            if prop.chosen is None:
                if current is not None:
                    self._set(current, BookingStatus.cancelled)
                    log("schedule_released", f"Released the held slot for {wo.id}: it no longer fits")
                for w in prop.warnings:
                    self._log_once(incident_id, "schedule_warning", w, as_of)
                return None
            ch = prop.chosen
            if current is not None and (current.start, current.technician_id) == (ch.start, ch.technician_id):
                return current
            now = utcnow()
            title = f"{wo.title} ({wo.id})"
            if current is None:
                b = Booking(id=self.store.next_id("BK"), incident_id=incident_id, work_order_id=wo.id, machine_id=inc.machine_id,
                            technician_id=ch.technician_id, technician_name=ch.technician_name, title=title,
                            start=ch.start, end=ch.end, window_label=ch.window_label, status=BookingStatus.tentative,
                            rationale=prop.rationale, created_at=now, updated_at=now)
                self._bookings[b.id] = b
                log("schedule_hold", f"Held {_fmt(ch.start)} to {ch.end:%H:%M} with {ch.technician_name} for work order "
                                     f"{wo.id} (tentative until the work order is approved)")
            else:
                b = current
                b.start, b.end, b.technician_id, b.technician_name = ch.start, ch.end, ch.technician_id, ch.technician_name
                b.window_label, b.rationale, b.updated_at = ch.window_label, prop.rationale, now
                log("schedule_moved", f"Moved the held slot to {_fmt(ch.start)} with {ch.technician_name}")
            wo.window_start, wo.window_end = b.start, b.end
            return b

    def _log_once(self, incident_id: str, kind: str, text: str, as_of) -> None:
        if not any(e.kind == kind and e.text == text for e in self.store.activity_for(incident_id)):
            self.store.log(incident_id, "ghostshift", "GhostShift", kind, text, as_of)

    # ------------------------------------------------------------- lifecycle
    def _dispatch_approved(self, b: Booking) -> bool:
        inc = self.store.incidents.get(b.incident_id)
        if inc is None:
            return False
        return any(self.store.actions[a].kind.value == "dispatch_work_order"
                   and self.store.actions[a].status in (ActionStatus.approved, ActionStatus.completed_simulated, ActionStatus.completed)
                   for a in inc.action_ids)

    def _set(self, b: Booking, status: BookingStatus) -> None:
        b.status, b.updated_at = status, utcnow()

    def confirm(self, booking_id: str, *, actor: str = "person", actor_name: str = "Supervisor") -> Booking:
        with self.store.lock:
            b = self.booking(booking_id)
            if b.status == BookingStatus.cancelled:
                raise ScheduleError(409, "booking_cancelled", "This booking was cancelled")
            if b.status == BookingStatus.confirmed:
                return b
            if not self._dispatch_approved(b):
                raise ScheduleError(409, "approval_required",
                                    "The work order must be approved before the slot can be confirmed")
            self._set(b, BookingStatus.confirmed)
            self.store.log(b.incident_id, actor, actor_name, "schedule_confirmed",
                           f"Confirmed {_fmt(b.start)} with {b.technician_name} for work order {b.work_order_id}",
                           self._incident_clock(b.incident_id))
            return b

    def confirm_for_incident(self, incident_id: str) -> Booking | None:
        """Called when the work order's approvals are complete."""
        with self.store.lock:
            b = next(iter(self.bookings(incident_id=incident_id)), None)
            if b is None or b.status != BookingStatus.tentative:
                return b
            return self.confirm(b.id, actor="ghostshift", actor_name="GhostShift")

    def cancel(self, booking_id: str, *, actor_name: str = "Supervisor") -> Booking:
        with self.store.lock:
            b = self.booking(booking_id)
            if b.status == BookingStatus.cancelled:
                return b
            self._set(b, BookingStatus.cancelled)
            self.store.log(b.incident_id, "person", actor_name, "schedule_cancelled",
                           f"Cancelled the slot {_fmt(b.start)} for work order {b.work_order_id}",
                           self._incident_clock(b.incident_id))
            return b

    def reschedule(self, booking_id: str, start: datetime, technician_id: str | None = None, *,
                   actor_name: str = "Supervisor") -> Booking:
        with self.store.lock:
            b = self.booking(booking_id)
            if b.status == BookingStatus.cancelled:
                raise ScheduleError(409, "booking_cancelled", "This booking was cancelled")
            inc = self.store.incidents[b.incident_id]
            m = inc.maintenance
            duration = (b.end - b.start).total_seconds() / 3600
            skills = m.work_order.required_skills if m else []
            win = next((w for w in self.ref.windows_for(b.machine_id)
                        if w.start <= start and start + timedelta(hours=duration) <= w.end), None)
            as_of = self._incident_clock(b.incident_id) or utcnow()
            problems: list[str] = []
            if win is None:
                problems.append("The new time is not inside a planned maintenance window")
            ready = self._part_ready(b.incident_id)
            if ready and start < ready:
                problems.append(f"The part does not arrive until {_fmt(ready)}")
            rul = inc.prognostics.rul
            deadline = as_of + timedelta(hours=rul.lower_hours) if rul and rul.supportable and rul.lower_hours is not None else None
            tech, reasons, _ = self.check_slot(b.machine_id, start, duration, skills, technician_id=technician_id,
                                               exclude=b.id, deadline=deadline)
            problems += reasons
            if problems or tech is None:
                raise ScheduleError(409, "slot_not_allowed", "That time breaks a scheduling rule", {"reasons": problems})
            b.start, b.end, b.technician_id, b.technician_name = start, start + timedelta(hours=duration), tech.id, tech.name
            b.window_label, b.updated_at = win.label, utcnow()
            wo = self.store.work_orders.get(b.work_order_id)
            if wo:
                wo.window_start, wo.window_end = b.start, b.end
            self.store.log(b.incident_id, "person", actor_name, "schedule_moved",
                           f"Rescheduled work order {b.work_order_id} to {_fmt(b.start)} with {tech.name}",
                           self._incident_clock(b.incident_id))
            return b

    # -------------------------------------------------------------------- ics
    def ics(self, b: Booking) -> str:
        stamp = lambda t: t.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: E731
        status = "CONFIRMED" if b.status == BookingStatus.confirmed else "TENTATIVE"
        return "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//GhostShift//Simulated schedule//EN", "BEGIN:VEVENT",
            f"UID:{b.id}@ghostshift.local", f"DTSTAMP:{stamp(b.updated_at)}", f"DTSTART:{stamp(b.start)}",
            f"DTEND:{stamp(b.end)}", f"SUMMARY:{b.title}", f"STATUS:{status}",
            f"DESCRIPTION:Simulated booking from GhostShift. Technician: {b.technician_name}. {b.machine_id}.",
            "END:VEVENT", "END:VCALENDAR", ""])
