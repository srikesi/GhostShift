"""Mock inventory: stock per storeroom, suppliers and purchase orders on the replay clock.

Everything here is simulated. Purchase orders are created when a parts order is sent (by a
person, or by Autopilot within its rules). On-hand stock is reserved; otherwise the cheapest
supplier that arrives before the earliest estimated limit is chosen. A supplier order then
moves ordered -> confirmed -> shipped -> received as the replay clock advances, and the part
is issued (stock goes down) when the work order is released.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .schemas.common import utcnow
from .schemas.ops import (
    InventoryView,
    POEvent,
    POStatus,
    PurchaseOrder,
    ReorderSuggestion,
    StockLevel,
    Supplier,
)
from .state import Store

CONFIRM_AFTER = timedelta(hours=4)
TERMINAL = {POStatus.issued, POStatus.cancelled}


class InventoryService:
    def __init__(self, data_dir: Path, store: Store, *,
                 incident_clock: Callable[[str], datetime | None],
                 site_clock: Callable[[], datetime | None]):
        self.store = store
        self._incident_clock = incident_clock
        self._site_clock = site_clock
        self._data = json.loads((data_dir / "inventory.json").read_text(encoding="utf-8"))
        parts = json.loads((data_dir / "parts_catalog.json").read_text(encoding="utf-8"))["parts"]
        self._desc = {p["sku"]: p["description"] for p in parts}
        self.suppliers = [Supplier.model_validate(s) for s in self._data["suppliers"]]
        self.listeners: list[Callable[[str], None]] = []  # called with an incident id when its part timing changes
        self.reset()

    def _now(self, incident_id: str | None = None) -> datetime | None:
        t = (self._incident_clock(incident_id) if incident_id else None) or self._site_clock()
        return None if t is None else t + self.skew

    def advance(self, hours: float) -> datetime | None:
        """Fast-forward the supply clock (the telemetry replay ends before most parts would arrive)."""
        with self.store.lock:
            self.skew += timedelta(hours=hours)
        self.sync()
        return self._now()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        with self.store.lock:
            self._stock = {s["sku"]: dict(s, reserved=0) for s in self._data["stock"]}
            self._orders: dict[str, PurchaseOrder] = {}
            self._seq = 0
            self._release_pending: set[str] = set()
            self._warned: set[str] = set()
            self.skew = timedelta(0)  # demo fast-forward added to the replay clock (telemetry ends before parts arrive)
            for o in self._data["open_orders"]:
                self._add_seed_order(o)

    def _add_seed_order(self, o: dict) -> None:
        sup = self._supplier(o["supplier_id"])
        ordered, eta = _dt(o["ordered_at"]), _dt(o["eta"])
        timeline = self._supplier_timeline(ordered, eta, sup.name if sup else "supplier")
        po = PurchaseOrder(
            id=o["id"], kind="supplier", sku=o["sku"], description=self._desc.get(o["sku"], o["sku"]),
            quantity=o["quantity"], incident_id=None, requisition_id=None, work_order_id=None,
            supplier_id=o["supplier_id"], supplier_name=sup.name if sup else None,
            unit_price_usd=o["unit_price_usd"], total_usd=round(o["unit_price_usd"] * o["quantity"], 2),
            status=POStatus.ordered, storeroom=self._stock[o["sku"]]["storeroom"], ordered_at=ordered, eta=eta,
            choice_reasons=["Restock order placed before this incident"], timeline=timeline)
        self._orders[po.id] = po

    def _supplier(self, supplier_id: str | None) -> Supplier | None:
        return next((s for s in self.suppliers if s.id == supplier_id), None)

    # ---------------------------------------------------------------- queries
    def stock_for(self, sku: str) -> dict | None:
        return self._stock.get(sku)

    def on_hand(self, sku: str) -> int | None:
        row = self._stock.get(sku)
        return None if row is None else row["on_hand"]

    def order_for_incident(self, incident_id: str) -> PurchaseOrder | None:
        with self.store.lock:
            return next((o for o in self._orders.values() if o.incident_id == incident_id and o.status != POStatus.cancelled), None)

    def part_ready_at(self, incident_id: str) -> datetime | None:
        """When the incident's part is (or will be) in the storeroom, or None if no order exists."""
        po = self.order_for_incident(incident_id)
        if po is None:
            return None
        return po.ordered_at if po.kind == "reservation" else po.eta

    def orders(self) -> list[PurchaseOrder]:
        with self.store.lock:
            return list(self._orders.values())

    def order(self, po_id: str) -> PurchaseOrder | None:
        return self._orders.get(po_id)

    def view(self) -> InventoryView:
        self.sync()
        with self.store.lock:
            stock = [self._level(r) for r in self._stock.values()]
            orders = sorted(self._orders.values(), key=lambda o: (o.status in TERMINAL, o.ordered_at))
            return InventoryView(as_of=self._now(), stock=stock, open_orders=orders,
                                 reorder_suggestions=self.reorder_suggestions(), suppliers=self.suppliers)

    def _level(self, r: dict) -> StockLevel:
        available = r["on_hand"] - r["reserved"]
        return StockLevel(sku=r["sku"], description=self._desc.get(r["sku"], r["sku"]), storeroom=r["storeroom"],
                          on_hand=r["on_hand"], reserved=r["reserved"], available=available, min=r["min"],
                          reorder_qty=r["reorder_qty"], below_min=r["min"] > 0 and available < r["min"])

    def reorder_suggestions(self) -> list[ReorderSuggestion]:
        out: list[ReorderSuggestion] = []
        with self.store.lock:
            for r in self._stock.values():
                available = r["on_hand"] - r["reserved"]
                incoming = sum(o.quantity for o in self._orders.values()
                               if o.sku == r["sku"] and o.kind == "supplier"
                               and o.status in (POStatus.ordered, POStatus.confirmed, POStatus.shipped)
                               and o.incident_id is None)
                if r["min"] <= 0 or available + incoming >= r["min"]:
                    continue
                offer = self._cheapest_offer(r["sku"])
                qty = r["reorder_qty"]
                out.append(ReorderSuggestion(
                    sku=r["sku"], description=self._desc.get(r["sku"], r["sku"]), storeroom=r["storeroom"],
                    available=available, min=r["min"], suggested_qty=qty,
                    supplier_name=offer[0].name if offer else None,
                    unit_price_usd=offer[1].unit_price_usd if offer else None,
                    lead_days=offer[1].lead_days if offer else None,
                    estimated_cost_usd=round(offer[1].unit_price_usd * qty, 2) if offer else None,
                    reason=f"{available} available, below the minimum of {r['min']}"))
        return out

    def _cheapest_offer(self, sku: str):
        offers = [(s, o) for s in self.suppliers for o in s.offers if o.sku == sku]
        return min(offers, key=lambda so: (so[1].unit_price_usd, so[1].lead_days), default=None)

    # ----------------------------------------------------------------- orders
    def place_order(self, requisition_id: str) -> PurchaseOrder:
        """Create the purchase order for a sent parts order (idempotent per requisition)."""
        with self.store.lock:
            existing = next((o for o in self._orders.values() if o.requisition_id == requisition_id), None)
            if existing:
                return existing
            req = self.store.requisitions[requisition_id]
            inc = self.store.incidents.get(req.incident_id)
            now = self._now(req.incident_id) or utcnow()
            row = self._stock.get(req.sku)
            self._seq += 1
            po_id = f"SIM-PO-{self._seq:05d}"
            base = dict(id=po_id, sku=req.sku, description=req.description or self._desc.get(req.sku, req.sku),
                        quantity=req.quantity, incident_id=req.incident_id, requisition_id=requisition_id,
                        work_order_id=inc.work_order_id if inc else None, ordered_at=now)
            if row is not None and row["on_hand"] - row["reserved"] >= req.quantity:
                row["reserved"] += req.quantity
                po = PurchaseOrder(
                    **base, kind="reservation", supplier_id=None, supplier_name=None, unit_price_usd=None,
                    total_usd=None, status=POStatus.reserved, storeroom=row["storeroom"], eta=now,
                    choice_reasons=[f"{row['on_hand']} on hand in {row['storeroom']}, so no supplier order is needed"],
                    timeline=[POEvent(status=POStatus.reserved, at=now,
                                      note=f"Reserved {req.quantity} from {row['storeroom']}")])
                text = f"Reserved {req.quantity} × {req.sku} from {row['storeroom']} ({po_id})"
            else:
                po = self._supplier_order(base, req, inc, now, row)
                when = po.eta.strftime("%a %d %b %H:%M UTC") if po.eta else "an unknown date"
                text = (f"Ordered {req.quantity} × {req.sku} from {po.supplier_name} "
                        f"(${po.total_usd:,.0f}, arrives {when}; {po_id})")
            self._orders[po.id] = po
            self.store.log(req.incident_id, "ghostshift", "GhostShift", "po_created", text, now)
            self._warn_if_low(po.sku, req.incident_id, now)
        self._notify(req.incident_id)
        return po

    def _supplier_order(self, base: dict, req, inc, now: datetime, row) -> PurchaseOrder:
        rul = inc.prognostics.rul if inc else None
        deadline = now + timedelta(hours=rul.lower_hours) if rul and rul.supportable and rul.lower_hours is not None else None
        offers = [(s, o) for s in self.suppliers for o in s.offers if o.sku == req.sku]
        reasons: list[str] = []
        if not offers:
            lead = 5.0
            reasons.append("No contract supplier lists this part; using the open-market distributor at list price")
            sup_id, sup_name, price = None, "Open-market distributor", req.estimated_cost_usd and req.estimated_cost_usd / req.quantity
            chosen_lead = lead
        else:
            def arrives(o): return now + timedelta(days=o[1].lead_days)
            in_time = [o for o in offers if deadline is None or arrives(o) <= deadline]
            pool = in_time or offers
            best = min(pool, key=lambda so: (so[1].unit_price_usd, -so[0].on_time_rate, so[1].lead_days))
            if not in_time:
                best = min(offers, key=lambda so: (so[1].lead_days, so[1].unit_price_usd))
                reasons.append("No supplier arrives before the earliest estimated limit; chose the fastest one. "
                               "Operations should decide whether to wait.")
            else:
                reasons.append("Cheapest supplier that arrives before the earliest estimated limit"
                               if deadline else "Cheapest supplier (no time-to-limit estimate to check against)")
            for s, o in offers:
                if (s, o) == best:
                    continue
                late = deadline is not None and arrives((s, o)) > deadline
                why = "arrives after the earliest limit" if late else f"costs more (${o.unit_price_usd:,.0f} vs ${best[1].unit_price_usd:,.0f})"
                if not late and o.unit_price_usd <= best[1].unit_price_usd:
                    why = "ranked lower on price and reliability"
                reasons.append(f"Not chosen: {s.name}, {o.lead_days:g} d at ${o.unit_price_usd:,.0f} ({why})")
            sup_id, sup_name, price, chosen_lead = best[0].id, best[0].name, best[1].unit_price_usd, best[1].lead_days
            reasons.append(f"{best[0].name} delivers on time {best[0].on_time_rate:.0%} of the time")
        eta = now + timedelta(days=chosen_lead)
        total = round(price * req.quantity, 2) if price is not None else None
        return PurchaseOrder(
            **base, kind="supplier", supplier_id=sup_id, supplier_name=sup_name, unit_price_usd=price, total_usd=total,
            status=POStatus.ordered, storeroom=row["storeroom"] if row else None, eta=eta, choice_reasons=reasons,
            timeline=self._supplier_timeline(now, eta, sup_name or "supplier"))

    @staticmethod
    def _supplier_timeline(ordered: datetime, eta: datetime, supplier: str) -> list[POEvent]:
        span = max(eta - ordered, timedelta(hours=1))
        confirm = ordered + min(CONFIRM_AFTER, span / 4)
        ship = ordered + span * 0.4
        return [
            POEvent(status=POStatus.ordered, at=ordered, note=f"Order sent to {supplier}"),
            POEvent(status=POStatus.confirmed, at=confirm, note=f"{supplier} confirmed the order", planned=True),
            POEvent(status=POStatus.shipped, at=ship, note="Shipped", planned=True),
            POEvent(status=POStatus.received, at=eta, note="Received into the storeroom", planned=True),
        ]

    # ------------------------------------------------------------------- time
    def sync(self) -> None:
        """Move orders along the replay clock; receive parts that have arrived."""
        changed: set[str] = set()
        with self.store.lock:
            for po in self._orders.values():
                if po.status in TERMINAL or po.kind != "supplier":
                    continue
                now = self._now(po.incident_id)
                if now is None:
                    continue
                for ev in po.timeline:
                    if ev.planned and ev.at <= now:
                        ev.planned = False
                        po.status = ev.status
                        if ev.status == POStatus.received:
                            self._receive(po)
                        if po.incident_id:
                            self.store.log(po.incident_id, "ghostshift", "GhostShift", f"po_{ev.status.value}",
                                           f"{po.id}: {ev.note}", ev.at)
                            changed.add(po.incident_id)
                if po.status == POStatus.received and po.incident_id in self._release_pending:
                    self._issue(po)
        for iid in changed:
            self._notify(iid)

    def _receive(self, po: PurchaseOrder) -> None:
        row = self._stock.get(po.sku)
        if row is None:
            return
        row["on_hand"] += po.quantity
        if po.incident_id:
            row["reserved"] += po.quantity

    def _issue(self, po: PurchaseOrder) -> None:
        row = self._stock.get(po.sku)
        now = self._now(po.incident_id) if po.incident_id else None
        if row is not None:
            row["on_hand"] -= po.quantity
            row["reserved"] = max(0, row["reserved"] - po.quantity)
        po.status = POStatus.issued
        po.timeline.append(POEvent(status=POStatus.issued, at=now or utcnow(),
                                   note=f"Issued to work order {po.work_order_id or ''}".strip()))
        self._release_pending.discard(po.incident_id)
        if po.incident_id:
            left = row["on_hand"] if row else 0
            self.store.log(po.incident_id, "ghostshift", "GhostShift", "po_issued",
                           f"Issued {po.quantity} × {po.sku} to work order {po.work_order_id}; {left} left in stock", now)
            self._warn_if_low(po.sku, po.incident_id, now)

    def issue_for_incident(self, incident_id: str) -> None:
        """The work order was released: take the part out of stock, or do it on arrival."""
        with self.store.lock:
            po = self.order_for_incident(incident_id)
            if po is None or po.status == POStatus.issued:
                return
            if po.status in (POStatus.reserved, POStatus.received):
                self._issue(po)
            else:
                self._release_pending.add(incident_id)
                self.store.log(incident_id, "ghostshift", "GhostShift", "po_waiting",
                               f"Part {po.sku} has not arrived yet; it will be issued to the work order when it does",
                               self._now(incident_id))

    def _warn_if_low(self, sku: str, incident_id: str, now) -> None:
        row = self._stock.get(sku)
        if row is None or row["min"] <= 0:
            return
        available = row["on_hand"] - row["reserved"]
        if available < row["min"] and sku not in self._warned:
            self._warned.add(sku)
            self.store.log(incident_id, "ghostshift", "GhostShift", "reorder",
                           f"Stock of {sku} is {available}, below the minimum of {row['min']}: reorder suggested "
                           f"({row['reorder_qty']} units)", now)

    def _notify(self, incident_id: str) -> None:
        for fn in self.listeners:
            fn(incident_id)


def _dt(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
