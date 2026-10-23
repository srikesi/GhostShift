"""Approving the work order from the phone page uses the same gate as the dashboard."""

from .conftest import CRAH, seek


def setup(client):
    iid = seek(client, CRAH, 216)["triggered_incident_id"]
    url = client.get(f"/api/incidents/{iid}").json()["notifications"][0]["inspection_url"]
    return iid, url.rsplit("/m/", 1)[1]


def body(**kw):
    return {"role": "maintenance_supervisor", "approver_name": "Sam Lee", "decision": "approve",
            "isolation_attestation": True, **kw}


def test_phone_approval_needs_the_lockout_checkbox(client):
    _, t = setup(client)
    r = client.post(f"/api/inspect/{t}/work-order/decision", json=body(isolation_attestation=False))
    assert r.status_code == 422 and r.json()["error"]["code"] == "isolation_attestation_required"


def test_phone_approval_then_release_confirms_the_slot(client):
    iid, t = setup(client)
    info = client.get(f"/api/inspect/{t}/work-order").json()
    assert info["action"]["status"] == "awaiting_approval" and info["title"]
    assert client.post(f"/api/inspect/{t}/work-order/release", json={"approver_name": "Sam Lee"}).status_code == 409
    r = client.post(f"/api/inspect/{t}/work-order/decision", json=body())
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]["status"] == "confirmed"
    done = client.post(f"/api/inspect/{t}/work-order/release", json={"approver_name": "Sam Lee"})
    assert done.status_code == 200 and done.json()["status"] in ("completed", "completed_simulated")


def test_wrong_role_a_second_decision_and_bad_links_are_refused(client):
    _, t = setup(client)
    assert client.post(f"/api/inspect/{t}/work-order/decision", json=body(role="operations_manager")).status_code == 403
    assert client.post(f"/api/inspect/{t}/work-order/decision", json=body()).status_code == 200
    assert client.post(f"/api/inspect/{t}/work-order/decision", json=body()).status_code == 409
    assert client.get("/api/inspect/nope/work-order").status_code == 404
    assert client.post("/api/inspect/nope/work-order/decision", json=body()).status_code == 404


def test_phone_can_reject(client):
    _, t = setup(client)
    r = client.post(f"/api/inspect/{t}/work-order/decision", json=body(decision="reject", isolation_attestation=False))
    assert r.status_code == 200 and r.json()["status"] == "rejected"
