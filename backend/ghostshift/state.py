"""In-memory application state for the demo.

A single lock guards all mutation. Swap for SQLite/DynamoDB by implementing the
same methods if durable persistence becomes necessary.
"""

from __future__ import annotations

import hashlib
import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock

from .schemas.common import utcnow
from .schemas.workflow import (
    ActivityEvent,
    AutonomySettings,
    Incident,
    Notification,
    ProposedAction,
    Requisition,
    WorkflowRun,
    WorkOrder,
)


@dataclass
class InspectionGrant:
    incident_id: str
    expires_at: datetime


@dataclass
class Store:
    lock: RLock = field(default_factory=RLock)
    cursors: dict[str, int] = field(default_factory=dict)
    runs: dict[str, WorkflowRun] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)
    actions: dict[str, ProposedAction] = field(default_factory=dict)
    requisitions: dict[str, Requisition] = field(default_factory=dict)
    work_orders: dict[str, WorkOrder] = field(default_factory=dict)
    notifications: dict[str, Notification] = field(default_factory=dict)
    # sha256(token) -> grant. Raw tokens are never stored here.
    grants: dict[str, InspectionGrant] = field(default_factory=dict)
    notified_tier: dict[str, str] = field(default_factory=dict)
    activity: list[ActivityEvent] = field(default_factory=list)
    # Runtime autonomy setting (kept across demo resets; set from config at startup).
    autonomy: AutonomySettings | None = None
    _seq: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def next_id(self, prefix: str) -> str:
        with self.lock:
            self._seq[prefix] += 1
            return f"{prefix}-{self._seq[prefix]:04d}"

    def reset(self) -> None:
        with self.lock:
            for d in (self.cursors, self.runs, self.incidents, self.actions, self.requisitions,
                      self.work_orders, self.notifications, self.grants, self.notified_tier, self.activity):
                d.clear()
            self._seq.clear()

    def log(self, incident_id: str, actor: str, actor_name: str, kind: str, text: str,
            machine_time: datetime | None) -> ActivityEvent:
        with self.lock:
            ev = ActivityEvent(id=self.next_id("EV"), incident_id=incident_id, at=utcnow(), machine_time=machine_time,
                               actor=actor, actor_name=actor_name, kind=kind, text=text)
            self.activity.append(ev)
            return ev

    def activity_for(self, incident_id: str) -> list[ActivityEvent]:
        with self.lock:
            return [e for e in self.activity if e.incident_id == incident_id]

    def open_incident_for(self, machine_id: str) -> Incident | None:
        with self.lock:
            return next((i for i in self.incidents.values() if i.machine_id == machine_id and i.status == "open"), None)

    # Inspection links ---------------------------------------------------------
    def issue_grant(self, incident_id: str, ttl_hours: float) -> tuple[str, InspectionGrant]:
        token = secrets.token_urlsafe(18)
        grant = InspectionGrant(incident_id=incident_id, expires_at=utcnow() + timedelta(hours=ttl_hours))
        with self.lock:
            self.grants[_hash(token)] = grant
        return token, grant

    def resolve_grant(self, token: str) -> InspectionGrant | None:
        with self.lock:
            grant = self.grants.get(_hash(token))
        if grant is None or grant.expires_at <= utcnow():
            return None
        return grant


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
