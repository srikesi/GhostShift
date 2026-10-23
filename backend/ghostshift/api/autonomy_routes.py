"""Autonomy setting: how much GhostShift may do without a person.

GET returns the current setting; PUT changes it at runtime (for demos) and applies it
to open incidents straight away. Safety tiers and the physical-work gate never change.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..schemas.workflow import AutonomySettings, AutonomyUpdate
from .routes import get_container

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


@router.get("", response_model=AutonomySettings)
def get_autonomy(c=Depends(get_container)):
    return c.store.autonomy


@router.put("", response_model=AutonomySettings)
def set_autonomy(body: AutonomyUpdate, c=Depends(get_container)):
    with c.store.lock:
        limit = body.auto_order_limit_usd if body.auto_order_limit_usd is not None else c.store.autonomy.auto_order_limit_usd
        c.store.autonomy = AutonomySettings(level=body.level, auto_order_limit_usd=limit)
    c.orchestrator.autopilot_sweep()
    return c.store.autonomy
