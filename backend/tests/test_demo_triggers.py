"""Demo triggers must text a link that actually opens the technician page."""

import re

import pytest

from .conftest import CH, CRAH, make_settings
from ghostshift.container import build_container
from ghostshift.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def phone_client():
    c = build_container(make_settings(demo_technician_phone="+15125550100"))
    return TestClient(create_app(c))


@pytest.mark.parametrize("machine", [CRAH, CH])
@pytest.mark.parametrize("path,body", [("inject-fault", {"fault_type": "mild"}), ("inject-fault", {"fault_type": "critical"}), ("emergency-stop", None)])
def test_trigger_text_has_a_working_link(phone_client, machine, path, body):
    r = phone_client.post(f"/api/machines/{machine}/{path}", json=body) if body else phone_client.post(f"/api/machines/{machine}/{path}")
    assert r.status_code == 200, r.text
    link = re.search(r"https?://\S+", r.json()["sms_sent"]).group(0).rstrip("|")
    assert "/m/" in link
    token = link.rsplit("/m/", 1)[1]
    assert phone_client.get(f"/api/inspect/{token}").status_code == 200


def test_breakdown_and_emergency_stop_call_straight_away_but_mild_does_not():
    c = build_container(make_settings(scheduler_call_phone="+15125550123"))
    client = TestClient(create_app(c))
    mild = client.post(f"/api/machines/{CRAH}/inject-fault", json={"fault_type": "mild"}).json()
    assert mild["call"] is None and client.get("/api/calendar/calls").json() == []
    r = client.post(f"/api/machines/{CRAH}/inject-fault", json={"fault_type": "critical"}).json()
    assert r["call"] and r["call"]["status"] == "in_progress"
    calls = client.get("/api/calendar/calls").json()
    assert len(calls) == 1 and "Hello, this is GhostShift scheduling" in calls[0]["transcript"][0]["text"]
    assert len(client.get("/api/calendar/calls").json()) == 1


def test_emergency_stop_calls_too():
    c = build_container(make_settings(scheduler_call_phone="+15125550123"))
    client = TestClient(create_app(c))
    stop = client.post(f"/api/machines/{CRAH}/emergency-stop").json()
    assert stop["call"] and len(client.get("/api/calendar/calls").json()) == 1


def test_trigger_still_works_with_no_phone_to_call(phone_client):
    r = phone_client.post(f"/api/machines/{CRAH}/inject-fault", json={"fault_type": "critical"})
    assert r.status_code == 200 and r.json()["call"] is None
