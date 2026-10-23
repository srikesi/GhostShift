"""Calendar and inventory endpoints (all data simulated)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from ..calendar_service import ScheduleError
from ..schemas.ops import (
    Booking,
    CalendarView,
    InventoryView,
    ProposeRequest,
    PurchaseOrder,
    RescheduleRequest,
    ReorderSuggestion,
    ScheduleProposal,
    StockLevel,
)
from typing import Literal

from pydantic import Field

from ..schemas.agents import ApproverRole
from ..schemas.common import Contract, utcnow
from ..schemas.workflow import DecisionRequest
from .routes import get_container

calendar_router = APIRouter(prefix="/api/calendar", tags=["calendar"])
inventory_router = APIRouter(prefix="/api/inventory", tags=["inventory"])
inspect_router = APIRouter(prefix="/api/inspect", tags=["inspection"])


def _sched(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except ScheduleError as exc:
        from ..approvals import GateError
        raise GateError(exc.status_code, exc.code, exc.message, exc.details) from exc


# ------------------------------------------------------------------ calendar
@calendar_router.get("/events", response_model=CalendarView)
def events(start: datetime | None = None, end: datetime | None = None, machine_id: str | None = None,
           c=Depends(get_container)):
    start = start or c.orchestrator.site_time() or utcnow()
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = end or start + timedelta(days=7)
    return c.calendar.view(start, end, machine_id)


@calendar_router.get("/bookings", response_model=list[Booking])
def bookings(incident_id: str | None = None, c=Depends(get_container)):
    return c.calendar.bookings(incident_id=incident_id)


@calendar_router.post("/propose", response_model=ScheduleProposal)
def propose(body: ProposeRequest, c=Depends(get_container)):
    wo = c.store.work_orders.get(body.work_order_id)
    if wo is None:
        raise HTTPException(404, f"Work order '{body.work_order_id}' not found")
    existing = next(iter(c.calendar.bookings(incident_id=wo.incident_id)), None)
    return c.calendar.proposal_for_incident(wo.incident_id, exclude=existing.id if existing else None)


@calendar_router.post("/holds", response_model=Booking | None, status_code=201)
def hold(body: ProposeRequest, c=Depends(get_container)):
    wo = c.store.work_orders.get(body.work_order_id)
    if wo is None:
        raise HTTPException(404, f"Work order '{body.work_order_id}' not found")
    return c.calendar.sync_incident(wo.incident_id)


@calendar_router.post("/bookings/{booking_id}/confirm", response_model=Booking)
def confirm(booking_id: str, c=Depends(get_container)):
    return _sched(c.calendar.confirm, booking_id)


@calendar_router.post("/bookings/{booking_id}/reschedule", response_model=Booking)
def reschedule(booking_id: str, body: RescheduleRequest, c=Depends(get_container)):
    return _sched(c.calendar.reschedule, booking_id, body.start, body.technician_id)


@calendar_router.post("/bookings/{booking_id}/cancel", response_model=Booking)
def cancel(booking_id: str, c=Depends(get_container)):
    return _sched(c.calendar.cancel, booking_id)


@calendar_router.get("/bookings/{booking_id}/ics")
def ics(booking_id: str, c=Depends(get_container)):
    b = _sched(c.calendar.booking, booking_id)
    return Response(c.calendar.ics(b), media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{b.id}.ics"'})


# ----------------------------------------------------------------- inventory
@inventory_router.get("", response_model=InventoryView)
def inventory(c=Depends(get_container)):
    return c.inventory.view()


@inventory_router.get("/stock", response_model=list[StockLevel])
def stock(c=Depends(get_container)):
    return c.inventory.view().stock


@inventory_router.get("/orders", response_model=list[PurchaseOrder])
def orders(incident_id: str | None = None, c=Depends(get_container)):
    c.inventory.sync()
    return [o for o in c.inventory.orders() if incident_id in (None, o.incident_id)]


@inventory_router.get("/orders/{po_id}", response_model=PurchaseOrder)
def order(po_id: str, c=Depends(get_container)):
    c.inventory.sync()
    po = c.inventory.order(po_id)
    if po is None:
        raise HTTPException(404, f"Purchase order '{po_id}' not found")
    return po


class AdvanceRequest(Contract):
    hours: float = Field(gt=0, le=24 * 14)


@inventory_router.post("/advance", response_model=InventoryView)
def advance(body: AdvanceRequest, c=Depends(get_container)):
    """Fast-forward the supply clock (simulated). Orders move along and arrived parts are received."""
    c.inventory.advance(body.hours)
    return c.inventory.view()


@inventory_router.get("/reorder-suggestions", response_model=list[ReorderSuggestion])
def reorder(c=Depends(get_container)):
    return c.inventory.reorder_suggestions()


# --------------------------------------------------------------- phone page
@inspect_router.get("/{token}/plan")
def plan(token: str, c=Depends(get_container)):
    """Scheduled time, technician and part status for the phone page (same token as the inspection link)."""
    grant = c.store.resolve_grant(token)
    if grant is None:
        raise HTTPException(404, "Link not found or expired")
    c.inventory.sync()
    booking = next(iter(c.calendar.bookings(incident_id=grant.incident_id)), None)
    po = c.inventory.order_for_incident(grant.incident_id)
    return {
        "booking": booking.model_dump(mode="json") if booking else None,
        "order": po.model_dump(mode="json") if po else None,
    }


# ------------------------------------------------ approve the work order from the phone
def _grant_incident(c, token: str) -> str:
    grant = c.store.resolve_grant(token)
    if grant is None:
        raise HTTPException(404, "Link not found or expired")
    return grant.incident_id


def _wo_action(c, incident_id: str):
    inc = c.store.incidents.get(incident_id)
    act = next((c.store.actions[a] for a in (inc.action_ids if inc else []) if c.store.actions[a].kind.value == "dispatch_work_order"), None)
    if act is None:
        raise HTTPException(404, "This problem has no work order to approve")
    return act


class PhoneDecision(Contract):
    role: ApproverRole
    approver_name: str = Field(min_length=2, max_length=80)
    decision: Literal["approve", "reject"]
    isolation_attestation: bool = False


class PhoneRelease(Contract):
    approver_name: str = Field(min_length=2, max_length=80)


@inspect_router.get("/{token}/work-order")
def phone_work_order(token: str, c=Depends(get_container)):
    act = _wo_action(c, _grant_incident(c, token))
    wo = c.store.work_orders.get(act.target_id)
    return {"action": act.model_dump(mode="json"), "title": wo.title if wo else None}


@inspect_router.post("/{token}/work-order/decision")
def phone_decide(token: str, body: PhoneDecision, c=Depends(get_container)):
    """Same approval gate as the dashboard: role check, lockout/tagout attestation, one decision per role."""
    act = _wo_action(c, _grant_incident(c, token))
    done = c.approvals.decide(act.id, DecisionRequest(role=body.role, approver_name=body.approver_name,
                                                      decision=body.decision, isolation_attestation=body.isolation_attestation,
                                                      note="Decided on the phone page"))
    return done.model_dump(mode="json")


@inspect_router.post("/{token}/work-order/release")
def phone_release(token: str, body: PhoneRelease, c=Depends(get_container)):
    act = _wo_action(c, _grant_incident(c, token))
    done = c.approvals.execute(act.id, actor="person", actor_name=body.approver_name)
    return done.model_dump(mode="json")
