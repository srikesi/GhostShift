"""The human approval gate is enforced in backend logic and cannot be bypassed."""

from __future__ import annotations

from .conftest import CRAH, seek


def _incident(client, cursor=216):
    r = seek(client, CRAH, cursor)
    view = client.get(f"/api/incidents/{r['triggered_incident_id']}").json()
    return view, {a["kind"]: a for a in view["actions"]}


def decide(client, action_id, role, decision="approve", attest=False):
    return client.post(f"/api/actions/{action_id}/decision", json={
        "role": role, "approver_name": "J. Rivera", "decision": decision, "isolation_attestation": attest})


def test_unapproved_action_cannot_execute(client):
    _, actions = _incident(client)
    for a in actions.values():
        r = client.post(f"/api/actions/{a['id']}/execute")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "approval_required"
    assert all(r["status"] == "awaiting_approval" for r in client.get("/api/requisitions").json())


def test_wrong_role_cannot_approve(client):
    _, actions = _incident(client)
    r = decide(client, actions["submit_requisition"]["id"], "operations_manager")
    assert r.status_code == 403 and r.json()["error"]["code"] == "role_not_permitted"
    assert client.post(f"/api/actions/{actions['submit_requisition']['id']}/execute").status_code == 409


def test_unknown_role_is_rejected_by_schema(client):
    _, actions = _incident(client)
    r = decide(client, actions["submit_requisition"]["id"], "intern")
    assert r.status_code == 422


def test_work_order_requires_isolation_attestation(client):
    _, actions = _incident(client)
    wo = actions["dispatch_work_order"]["id"]
    r = decide(client, wo, "maintenance_supervisor", attest=False)
    assert r.status_code == 422 and r.json()["error"]["code"] == "isolation_attestation_required"
    r = decide(client, wo, "maintenance_supervisor", attest=True)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert r.json()["isolation_attested_by"] == "J. Rivera"


def test_rejected_action_cannot_execute_or_be_reapproved(client):
    _, actions = _incident(client)
    req = actions["submit_requisition"]["id"]
    assert decide(client, req, "maintenance_supervisor", "reject").json()["status"] == "rejected"
    assert client.post(f"/api/actions/{req}/execute").status_code == 409
    assert decide(client, req, "maintenance_supervisor").status_code == 409
    assert client.get("/api/requisitions").json()[0]["status"] == "rejected"


def test_approved_action_completes_as_simulated(client):
    view, actions = _incident(client)
    req = actions["submit_requisition"]["id"]
    assert decide(client, req, "maintenance_supervisor").json()["status"] == "approved"
    r = client.post(f"/api/actions/{req}/execute")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed_simulated" and body["external_reference"].startswith("SIM-PO-")
    assert "No order was placed" in body["result_note"]
    assert client.post(f"/api/actions/{req}/execute").status_code == 409  # not twice
    assert client.get("/api/requisitions").json()[0]["status"] == "submitted_simulated"


def test_partial_approval_blocks_execution(client):
    # At critical tier the work order needs maintenance AND operations approval.
    _, actions = _incident(client, cursor=239)
    wo = actions["dispatch_work_order"]
    assert {a["role"] for a in wo["approvals"]} == {"maintenance_supervisor", "operations_manager"}
    r = decide(client, wo["id"], "maintenance_supervisor", attest=True)
    assert r.json()["status"] == "awaiting_approval"
    r = client.post(f"/api/actions/{wo['id']}/execute")
    assert r.status_code == 409 and r.json()["error"]["details"]["pending_roles"] == ["operations_manager"]
    assert decide(client, wo["id"], "operations_manager", attest=True).json()["status"] == "approved"
    assert client.post(f"/api/actions/{wo['id']}/execute").json()["status"] == "completed_simulated"


def test_same_role_cannot_decide_twice(client):
    _, actions = _incident(client, cursor=239)
    wo = actions["dispatch_work_order"]["id"]
    decide(client, wo, "maintenance_supervisor", attest=True)
    r = decide(client, wo, "maintenance_supervisor", attest=True)
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_decided"


def test_unknown_action_404(client):
    assert client.post("/api/actions/ACT-9999/execute").status_code == 404
