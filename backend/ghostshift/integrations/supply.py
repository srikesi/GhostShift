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

    def candidates(self, *, component_type: str, machine_model: str) -> list[CatalogPart]:
        return [
            p for p in self._parts
            if component_type in p.component_types and any(machine_model.startswith(m) for m in p.machine_models)
        ]

    def health(self) -> ProviderHealth:
        return ProviderHealth(capability="parts_catalog", provider=self.info, configured=True, available=True,
                              detail=f"{len(self._parts)} fixture parts; stock and lead times are simulated")


class SimulatedProcurement:
    info = info("procurement-simulated", ProviderKind.stub)

    def __init__(self):
        self._seq = count(1)

    def submit_requisition(self, *, requisition_id: str, sku: str, quantity: int) -> SubmissionResult:
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
