// Calendar and inventory (all simulated). Mirrors backend/ghostshift/schemas/ops.py.
import { post, request } from "./client";

export interface Technician {
  id: string;
  name: string;
  role: string;
  skills: string[];
}

export interface CalendarEvent {
  id: string;
  kind: "maintenance_window" | "existing_job" | "ghostshift_hold" | "ghostshift_booking";
  title: string;
  machine_id: string | null;
  technician_id: string | null;
  start: string;
  end: string;
  status: string;
  work_order_id: string | null;
}

export interface ShiftBlock {
  technician_id: string;
  start: string;
  end: string;
}

export interface CalendarView {
  start: string;
  end: string;
  technicians: Technician[];
  events: CalendarEvent[];
  shifts: ShiftBlock[];
  redundancy: { unit: string; partner: string; rule: string }[];
}

export interface SlotOption {
  window_label: string;
  window_start: string;
  window_end: string;
  start: string | null;
  end: string | null;
  technician_id: string | null;
  technician_name: string | null;
  feasible: boolean;
  reasons: string[];
}

export interface ScheduleProposal {
  status: "fits" | "no_fit";
  machine_id: string;
  chosen: SlotOption | null;
  rationale: string[];
  alternatives: SlotOption[];
  warnings: string[];
  constraints: {
    duration_hours: number;
    required_skills: string[];
    part_ready: string | null;
    must_finish_before: string | null;
    redundant_unit: string | null;
  };
}

export interface Booking {
  id: string;
  incident_id: string;
  work_order_id: string;
  machine_id: string;
  technician_id: string;
  technician_name: string;
  title: string;
  start: string;
  end: string;
  window_label: string;
  status: "tentative" | "confirmed" | "cancelled";
  rationale: string[];
}

export interface StockLevel {
  sku: string;
  description: string;
  storeroom: string;
  on_hand: number;
  reserved: number;
  available: number;
  min: number;
  reorder_qty: number;
  below_min: boolean;
}

export type POStatus = "reserved" | "ordered" | "confirmed" | "shipped" | "received" | "issued" | "cancelled";

export interface POEvent {
  status: POStatus;
  at: string;
  note: string;
  planned: boolean;
}

export interface PurchaseOrder {
  id: string;
  kind: "supplier" | "reservation";
  sku: string;
  description: string;
  quantity: number;
  incident_id: string | null;
  supplier_name: string | null;
  unit_price_usd: number | null;
  total_usd: number | null;
  status: POStatus;
  storeroom: string | null;
  ordered_at: string;
  eta: string | null;
  choice_reasons: string[];
  timeline: POEvent[];
}

export interface ReorderSuggestion {
  sku: string;
  description: string;
  storeroom: string;
  available: number;
  min: number;
  suggested_qty: number;
  supplier_name: string | null;
  unit_price_usd: number | null;
  lead_days: number | null;
  estimated_cost_usd: number | null;
  reason: string;
}

export interface InventoryView {
  as_of: string | null;
  stock: StockLevel[];
  open_orders: PurchaseOrder[];
  reorder_suggestions: ReorderSuggestion[];
}

export interface PhonePlan {
  booking: Booking | null;
  order: PurchaseOrder | null;
}

export const ops = {
  calendar: (start?: string) => request<CalendarView>(`/api/calendar/events${start ? `?start=${encodeURIComponent(start)}` : ""}`),
  bookings: (incidentId?: string) =>
    request<Booking[]>(`/api/calendar/bookings${incidentId ? `?incident_id=${encodeURIComponent(incidentId)}` : ""}`),
  propose: (workOrderId: string) => post<ScheduleProposal>("/api/calendar/propose", { work_order_id: workOrderId }),
  reschedule: (bookingId: string, start: string) => post<Booking>(`/api/calendar/bookings/${bookingId}/reschedule`, { start }),
  cancel: (bookingId: string) => post<Booking>(`/api/calendar/bookings/${bookingId}/cancel`),
  hold: (workOrderId: string) => post<Booking | null>("/api/calendar/holds", { work_order_id: workOrderId }),
  icsUrl: (bookingId: string) => `/api/calendar/bookings/${bookingId}/ics`,
  inventory: () => request<InventoryView>("/api/inventory"),
  advance: (hours: number) => post<InventoryView>("/api/inventory/advance", { hours }),
  plan: (token: string) => request<PhonePlan>(`/api/inspect/${encodeURIComponent(token)}/plan`),
};
