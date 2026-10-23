"""Accepted texts are checked with Twilio; undelivered ones are shown as failed with a plain reason."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from ghostshift.container import build_container
from ghostshift.integrations.sms import TwilioSms
from ghostshift.main import create_app

from .conftest import CRAH, make_settings, seek


def twilio(final_status, code=None):
    def handler(req: httpx.Request):
        if req.method == "POST":
            return httpx.Response(201, json={"sid": "SM123"})
        return httpx.Response(200, json={"sid": "SM123", "status": final_status, "error_code": code, "error_message": None})

    return TwilioSms(account_sid="AC1", auth_token="t", from_number="+15125550000", override_to="+15125550100",
                     transport=httpx.MockTransport(handler), sleep=lambda _: None)


def test_delivery_status_mapping():
    assert twilio("delivered").delivery_status("SM123").state == "delivered"
    d = twilio("undelivered", 30034).delivery_status("SM123")
    assert d.state == "failed" and "A2P 10DLC" in d.error and "30034" in d.error
    assert twilio("sent").delivery_status("SM123").state == "pending"


def _client(sms):
    return TestClient(create_app(build_container(make_settings(mode="auto"), sms=sms)))


def test_check_endpoint_marks_undelivered_text_failed_and_logs_it():
    c = _client(twilio("undelivered", 30034))
    incident_id = seek(c, CRAH, 216)["triggered_incident_id"]
    n = c.get(f"/api/notifications?incident_id={incident_id}").json()[-1]
    assert n["status"] == "sent" and n["external_id"] == "SM123"
    checked = c.post(f"/api/notifications/{n['id']}/check").json()
    assert checked["status"] == "failed" and "A2P 10DLC" in checked["error"]
    activity = c.get(f"/api/incidents/{incident_id}").json()["activity"]
    assert activity[-1]["kind"] == "notify_failed"


def test_check_endpoint_marks_delivered():
    c = _client(twilio("delivered"))
    incident_id = seek(c, CRAH, 216)["triggered_incident_id"]
    n = c.get(f"/api/notifications?incident_id={incident_id}").json()[-1]
    assert c.post(f"/api/notifications/{n['id']}/check").json()["status"] == "delivered"


def test_check_is_a_no_op_for_simulated_texts(client):
    incident_id = seek(client, CRAH, 216)["triggered_incident_id"]
    n = client.get(f"/api/notifications?incident_id={incident_id}").json()[-1]
    assert client.post(f"/api/notifications/{n['id']}/check").json()["status"] == "simulated_sent"
    assert client.post("/api/notifications/SMS-9999/check").status_code == 404
