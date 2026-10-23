"""Contracts for scheduling (calendar) and inventory. All data behind these is simulated."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from .common import Contract

# --------------------------------------------------------------------- calendar


class Shift(Contract):
    days: list[int] = Field(description="Weekdays, 0 = Monday")
    start_hour: float
    end_hour: float = Field(description="Above 24 means the shift runs into the next day")


class Technician(Contract):
    id: str
    name: str
    role: str
    skills: list[str]
    shifts: list[Shift]


class FixtureBooking(Contract):
    id: str
    title: str
    machine_id: str | None
    technician_id: str | None
    start: datetime
    end: datetime


class RedundancyRule(Contract):
    unit: str
    partner: str
    rule: str


class BookingStatus(str, Enum):
    tentative = "tentative"
    confirmed = "confirmed"
    cancelled = "cancelled"


class CalendarEvent(Contract):
    id: str
    kind: Literal["maintenance_window", "existing_job", "ghostshift_hold", "ghostshift_booking"]
    title: str
    machine_id: str | None
    technician_id: str | None
    start: datetime
    end: datetime
    status: str = "planned"
    work_order_id: str | None = None
    simulated: bool = True


class ShiftBlock(Contract):
    technician_id: str
    start: datetime
    end: datetime


class CalendarView(Contract):
    start: datetime
    end: datetime
    technicians: list[Technician]
    events: list[CalendarEvent]
    shifts: list[ShiftBlock]
    redundancy: list[RedundancyRule]


class SlotOption(Contract):
    window_label: str
    window_start: datetime
    window_end: datetime
    start: datetime | None = None
    end: datetime | None = None
    technician_id: str | None = None
    technician_name: str | None = None
    feasible: bool
    reasons: list[str] = Field(default_factory=list)


class ScheduleConstraints(Contract):
    duration_hours: float
    required_skills: list[str]
    part_ready: datetime | None
    must_finish_before: datetime | None
    redundant_unit: str | None


class ScheduleProposal(Contract):
    status: Literal["fits", "no_fit"]
    machine_id: str
    chosen: SlotOption | None
    rationale: list[str]
    alternatives: list[SlotOption]
    warnings: list[str]
    constraints: ScheduleConstraints


class Booking(Contract):
    id: str
    incident_id: str
    work_order_id: str
    machine_id: str
    technician_id: str
    technician_name: str
    title: str
    start: datetime
    end: datetime
    window_label: str
    status: BookingStatus
    rationale: list[str]
    simulated: bool = True
    created_at: datetime
    updated_at: datetime


class ProposeRequest(Contract):
    work_order_id: str


class RescheduleRequest(Contract):
    start: datetime
    technician_id: str | None = None


# -------------------------------------------------------------------- inventory


class StockLevel(Contract):
    sku: str
    description: str
    storeroom: str
    on_hand: int
    reserved: int
    available: int
    min: int
    reorder_qty: int
    below_min: bool
    simulated: bool = True


class SupplierOffer(Contract):
    sku: str
    unit_price_usd: float
    lead_days: float


class Supplier(Contract):
    id: str
    name: str
    on_time_rate: float
    offers: list[SupplierOffer]


class POStatus(str, Enum):
    reserved = "reserved"
    ordered = "ordered"
    confirmed = "confirmed"
    shipped = "shipped"
    received = "received"
    issued = "issued"
    cancelled = "cancelled"


class POEvent(Contract):
    status: POStatus
    at: datetime
    note: str
    planned: bool = False  # true until the replay clock reaches it


class PurchaseOrder(Contract):
    id: str
    kind: Literal["supplier", "reservation"]
    sku: str
    description: str
    quantity: int
    incident_id: str | None
    requisition_id: str | None
    work_order_id: str | None
    supplier_id: str | None
    supplier_name: str | None
    unit_price_usd: float | None
    total_usd: float | None
    status: POStatus
    storeroom: str | None
    ordered_at: datetime
    eta: datetime | None
    choice_reasons: list[str]
    timeline: list[POEvent]
    simulated: bool = True


class ReorderSuggestion(Contract):
    sku: str
    description: str
    storeroom: str
    available: int
    min: int
    suggested_qty: int
    supplier_name: str | None
    unit_price_usd: float | None
    lead_days: float | None
    estimated_cost_usd: float | None
    reason: str
    simulated: bool = True


class InventoryView(Contract):
    as_of: datetime | None
    stock: list[StockLevel]
    open_orders: list[PurchaseOrder]
    reorder_suggestions: list[ReorderSuggestion]
    suppliers: list[Supplier]
