"""Floor plan layout for the home page (simulated layout data)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from ..schemas.common import Contract
from .routes import get_container

router = APIRouter(prefix="/api/floorplan", tags=["floorplan"])


class Zone(Contract):
    id: str
    label: str
    x: float
    y: float
    w: float
    h: float


class PlanLabel(Contract):
    text: str
    x: float
    y: float


class PlanUnit(Contract):
    id: str
    label: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    machine_id: str | None = None  # set when GhostShift monitors it; others are placeholders


class PlanLink(Contract):
    a: str
    b: str
    label: str


class FloorPlan(Contract):
    site: str
    width: float
    height: float
    zones: list[Zone]
    labels: list[PlanLabel]
    units: list[PlanUnit]
    links: list[PlanLink]


@router.get("", response_model=FloorPlan)
def floorplan(c=Depends(get_container)):
    raw = json.loads((c.settings.data_dir / "floorplan.json").read_text(encoding="utf-8"))
    raw.pop("_comment", None)
    plan = FloorPlan.model_validate(raw)
    known = set(c.telemetry.machine_ids())
    for u in plan.units:  # a unit only links to a machine that actually exists
        if u.machine_id not in known:
            u.machine_id = None
    return plan
