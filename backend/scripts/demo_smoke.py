"""End-to-end smoke test of the demo story against a running API.

    make api          # in one terminal
    make demo-smoke   # in another

Resets state, replays MF-07 from normal operation to the end, and checks that
each step of the story happens: detection, SMS, inspection link, approval gate.
Exits non-zero on the first failed expectation.
"""

from __future__ import annotations

import os
import sys

import httpx

API = os.environ.get("GHOSTSHIFT_API_URL", "http://127.0.0.1:8000")


def expect(cond: bool, msg: str) -> None:
    print(("✓ " if cond else "✗ ") + msg)
    if not cond:
        sys.exit(1)


def main() -> None:
    c = httpx.Client(base_url=API, timeout=10)
    try:
        health = c.get("/api/health").json()
    except httpx.HTTPError as exc:
        expect(False, f"API reachable at {API} ({exc})")
    expect(health["app"] == "GhostShift", f"API healthy, mode={health['mode']}")
    c.post("/api/demo/reset")

    m = c.get("/api/machines/MF-07").json()
    expect(m["summary"]["status"] == "normal", "MF-07 starts normal")

    tiers, incident_id = [], None
    while True:
        r = c.post("/api/machines/MF-07/replay", json={"action": "advance", "steps": 2}).json()
        if r["triggered_incident_id"]:
            incident_id = r["triggered_incident_id"]
            view = c.get(f"/api/incidents/{incident_id}").json()
            tier = view["incident"]["safety"]["risk_tier"]
            tiers.append((r["cursor"], tier))
            print(f"  sample {r['cursor']}: {r['screening_severity']} → {incident_id} tier={tier}")
        if r["cursor"] >= r["length"] - 1:
            break

    expect(incident_id is not None, "Deviation detected and incident opened")
    expect([t for _, t in tiers][0] == "elevated", "First detection is elevated (before any alarm limit)")
    expect(tiers[-1][1] == "critical", "Escalates to critical by end of replay")

    view = c.get(f"/api/incidents/{incident_id}").json()
    inc = view["incident"]
    expect(inc["affected_component_id"] == "fan_bearing", "Affected component: fan bearing")
    expect(inc["prognostics"]["rul"]["supportable"], "RUL estimate is supportable and qualified")
    expect(view["requisition"]["sku"] == "GS-BRG-FAN-KIT", "Part proposed: GS-BRG-FAN-KIT")
    expect(len(view["notifications"]) >= 2, "Technician SMS sent (high) and re-sent on escalation")
    token = view["notifications"][-1]["inspection_url"].rsplit("/m/", 1)[1]
    insp = c.get(f"/api/inspect/{token}")
    expect(insp.status_code == 200, "Mobile inspection link resolves")

    act = next(a for a in view["actions"] if a["kind"] == "dispatch_work_order")
    expect(c.post(f"/api/actions/{act['id']}/execute").status_code == 409, "Unapproved work order cannot execute")

    # Calendar and inventory, at High priority (one approver needed for each action).
    c.post("/api/demo/reset")
    r = c.post("/api/machines/MF-07/replay", json={"action": "seek", "cursor": 216}).json()
    incident_id = r["triggered_incident_id"]
    view = c.get(f"/api/incidents/{incident_id}").json()
    act = next(a for a in view["actions"] if a["kind"] == "dispatch_work_order")
    hold = c.get("/api/calendar/bookings", params={"incident_id": incident_id}).json()
    expect(len(hold) == 1 and hold[0]["status"] == "tentative", "Slot held tentatively with the work order")
    expect(c.post(f"/api/calendar/bookings/{hold[0]['id']}/confirm").status_code == 409, "Slot cannot be confirmed before approval")
    req_act = next(a for a in view["actions"] if a["kind"] == "submit_requisition")
    body = {"role": "maintenance_supervisor", "approver_name": "Smoke test", "decision": "approve"}
    expect(c.post(f"/api/actions/{req_act['id']}/decision", json=body).status_code == 200, "Parts order approved")
    done = c.post(f"/api/actions/{req_act['id']}/execute").json()
    po = c.get(f"/api/inventory/orders/{done['external_reference']}").json()
    expect(po["kind"] == "reservation" and po["status"] == "reserved", "Purchase order reserves the part in stock")
    attest = {**body, "isolation_attestation": True}
    expect(c.post(f"/api/actions/{act['id']}/decision", json=attest).status_code == 200, "Work order approved with lockout/tagout")
    booked = c.get("/api/calendar/bookings", params={"incident_id": incident_id}).json()[0]
    expect(booked["status"] == "confirmed", "Slot confirmed once the work order is approved")

    # Autonomy: with Autopilot on, the compressor's in-stock cleaning kit is ordered with no person involved.
    c.post("/api/demo/reset")
    before = c.get("/api/autonomy").json()["level"]
    c.put("/api/autonomy", json={"level": "autopilot"})
    r = c.post("/api/machines/CH-02/replay", json={"action": "seek", "cursor": 150}).json()
    cv = c.get(f"/api/incidents/{r['triggered_incident_id']}").json()
    req = next(a for a in cv["actions"] if a["kind"] == "submit_requisition")
    wo = next(a for a in cv["actions"] if a["kind"] == "dispatch_work_order")
    expect(req["status"] == "completed_simulated", "Autopilot placed the parts order on its own")
    expect(wo["status"] == "awaiting_approval", "Physical work still waits for a person")
    c.put("/api/autonomy", json={"level": before})
    c.post("/api/demo/reset")
    print("\nDemo story verified.")


if __name__ == "__main__":
    main()
