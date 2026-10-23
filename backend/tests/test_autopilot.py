"""Autopilot: GhostShift places eligible parts orders itself; physical work always waits for a person."""

from __future__ import annotations

from .conftest import CH, CRAH, seek


def autopilot(client, on=True, limit=None):
    body = {"level": "autopilot" if on else "advise"}
    if limit is not None:
        body["auto_order_limit_usd"] = limit
    r = client.put("/api/autonomy", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def view(client, incident_id):
    return client.get(f"/api/incidents/{incident_id}").json()


def action(v, kind):
    return next(a for a in v["actions"] if a["kind"] == kind)


def test_off_by_default_people_approve_everything(client):
    assert client.get("/api/autonomy").json() == {"level": "advise", "auto_order_limit_usd": 2500.0}
    v = view(client, seek(client, CRAH, 216)["triggered_incident_id"])
    assert action(v, "submit_requisition")["status"] == "awaiting_approval"
    kinds = [e["kind"] for e in v["activity"]]
    assert kinds[:4] == ["detected", "priority", "drafted", "scheduled"] and "notified" in kinds
    assert all(e["actor"] == "ghostshift" for e in v["activity"])
    assert all(e["machine_time"] for e in v["activity"])


def test_autopilot_orders_part_at_high_priority_but_not_physical_work(client):
    autopilot(client)
    first = seek(client, CRAH, 172)  # Medium priority
    v = view(client, first["triggered_incident_id"])
    assert action(v, "submit_requisition")["status"] == "awaiting_approval"
    assert any("waiting until priority is High" in e["text"] for e in v["activity"])

    seek(client, CRAH, 216)  # High priority
    v = view(client, first["triggered_incident_id"])
    req = action(v, "submit_requisition")
    assert req["status"] == "completed_simulated"
    assert req["approvals"][0]["automated"] is True and req["approvals"][0]["decided_by"] == "Auto-order policy"
    assert action(v, "dispatch_work_order")["status"] == "awaiting_approval"
    assert v["requisition"]["status"] == "submitted_simulated"
    assert "Part ordered." in v["notifications"][-1]["body"]
    policy = [e for e in v["activity"] if e["actor"] == "policy"]
    assert [e["kind"] for e in policy] == ["decision_approved", "executed"]
    assert any(e["kind"] == "handoff" for e in v["activity"])


def test_autopilot_never_releases_work_order_even_when_urgent(client):
    autopilot(client)
    r = seek(client, CRAH, 239)
    v = view(client, r["triggered_incident_id"])
    wo = action(v, "dispatch_work_order")
    assert wo["status"] == "awaiting_approval"
    assert all(a["decision"] == "pending" for a in wo["approvals"])
    assert client.post(f"/api/actions/{wo['id']}/execute").status_code == 409


def test_autopilot_holds_orders_over_the_limit(client):
    autopilot(client, limit=100)
    v = view(client, seek(client, CRAH, 216)["triggered_incident_id"])
    assert action(v, "submit_requisition")["status"] == "awaiting_approval"
    assert any("over the $100 auto-order limit" in e["text"] for e in v["activity"])


def test_switching_autopilot_on_applies_to_open_problems(client):
    incident_id = seek(client, CH, 150)["triggered_incident_id"]
    assert action(view(client, incident_id), "submit_requisition")["status"] == "awaiting_approval"
    autopilot(client)
    assert action(view(client, incident_id), "submit_requisition")["status"] == "completed_simulated"


def test_api_decisions_are_never_marked_automated(client):
    v = view(client, seek(client, CRAH, 216)["triggered_incident_id"])
    req = action(v, "submit_requisition")
    r = client.post(f"/api/actions/{req['id']}/decision", json={
        "role": "maintenance_supervisor", "approver_name": "Auto-order policy", "decision": "approve"})
    assert r.json()["approvals"][0]["automated"] is False
    events = view(client, v["incident"]["id"])["activity"]
    assert events[-1]["actor"] == "person" and events[-1]["machine_time"]


def test_reset_keeps_the_autonomy_setting(client):
    autopilot(client)
    client.post("/api/demo/reset")
    assert client.get("/api/autonomy").json()["level"] == "autopilot"
    assert client.get("/api/incidents").json() == []


def test_invalid_autonomy_level_rejected(client):
    assert client.put("/api/autonomy", json={"level": "yolo"}).status_code == 422
