"""Parts catalog, procurement and work-order (CMMS) providers.

Only simulated implementations exist today. A real ERP/CMMS adapter (e.g. SAP
PM, Maximo, Fiix, or an AWS-hosted API) implements the same Protocols from
`integrations.base` and is selected in `ghostshift.container`.
"""

from __future__ import annotations

import json
from itertools import count
from pathlib import Path

from ..schemas.common import ProviderKind, utcnow
from ..schemas.reference import CatalogPart
from .base import ProviderHealth, SubmissionResult, info


class FixturePartsCatalog:
    info = info("parts-catalog-fixture", ProviderKind.stub)

    def __init__(self, path: Path):
        self._path = path
        self._parts = [CatalogPart.model_validate(p) for p in json.loads(path.read_text())["parts"]]
        self._inventory = None

    def bind_inventory(self, inventory) -> None:
        """Use the live (simulated) storeroom counts for on-hand stock instead of the fixture's starting values."""
        self._inventory = inventory

    def candidates(self, *, component_type: str, machine_model: str) -> list[CatalogPart]:
        found = [
            p for p in self._parts
            if component_type in p.component_types and any(machine_model.startswith(m) for m in p.machine_models)
        ]
        if self._inventory is None:
            return found
        out = []
        for p in found:
            on_hand = self._inventory.on_hand(p.sku)
            if on_hand is None:
                out.append(p)
            else:
                out.append(p.model_copy(update={"availability": p.availability.model_copy(update={"on_hand": on_hand})}))
        return out

    def health(self) -> ProviderHealth:
        return ProviderHealth(capability="parts_catalog", provider=self.info, configured=True, available=True,
                              detail=f"{len(self._parts)} fixture parts; stock and lead times are simulated")


class SimulatedProcurement:
    info = info("procurement-simulated", ProviderKind.stub)

    def __init__(self):
        self._seq = count(1)
        self._inventory = None

    def bind(self, inventory) -> None:
        """Send orders into the mock inventory so they become purchase orders that progress on the replay clock."""
        self._inventory = inventory

    def submit_requisition(self, *, requisition_id: str, sku: str, quantity: int) -> SubmissionResult:
        if self._inventory is not None:
            po = self._inventory.place_order(requisition_id)
            if po.kind == "reservation":
                note = f"Simulated: reserved {po.quantity} from {po.storeroom}. No order was placed with a real vendor."
            else:
                note = (f"Simulated purchase order to {po.supplier_name}; it moves to received on the replay clock. "
                        "No order was placed with a real vendor.")
            return SubmissionResult(external_reference=po.id, simulated=True, note=note, submitted_at=po.ordered_at)
        return SubmissionResult(
            external_reference=f"SIM-PR-{next(self._seq):05d}",
            simulated=True,
            note="Simulated purchase requisition. No order was placed and no vendor was contacted.",
            submitted_at=utcnow(),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(capability="procurement", provider=self.info, configured=True, available=True,
                              detail="Simulated; no ERP connected")


class SimulatedWorkOrders:
    info = info("cmms-simulated", ProviderKind.stub)

    def __init__(self):
        self._seq = count(1)

    def dispatch(self, *, work_order_id: str, title: str, machine_id: str) -> SubmissionResult:
        return SubmissionResult(
            external_reference=f"SIM-WO-{next(self._seq):05d}",
            simulated=True,
            note="Simulated dispatch to the maintenance queue. No CMMS record was created.",
            submitted_at=utcnow(),
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth(capability="work_orders", provider=self.info, configured=True, available=True,
                              detail="Simulated; no CMMS connected")
