"""Scheduler calls: offer checked slots, understand replies, book the accepted slot, Autopilot confirms it."""

import httpx
import pytest
from fastapi.testclient import TestClient

from ghostshift.container import build_container
from ghostshift.main import create_app
from ghostshift.voice_calls import TwilioCalls, twilio_signature, understand

from .conftest import CRAH, make_settings, seek

PHONE = "+15125550123"


def make(**kw):
    c = build_container(make_settings(scheduler_call_phone=PHONE, **kw))
    return c, TestClient(create_app(c))


def incident(client, container, free_deadline=False):
    iid = seek(client, CRAH, 216)["triggered_incident_id"]
    if free_deadline:  # no time-to-limit estimate, so later windows fit too
        inc = container.store.incidents[iid]
        container.store.incidents[iid] = inc.model_copy(update={"prognostics": inc.prognostics.model_copy(update={"rul": None})})
        container.calendar.sync_incident(iid)
    return iid


def say(client, call_id, text):
    r = client.post(f"/api/voice/calls/{call_id}/say", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def start(client, iid):
    r = client.post("/api/calendar/call", json={"incident_id": iid})
    assert r.status_code == 201, r.text
    return r.json()


def booking(client, iid):
    return client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]


@pytest.mark.parametrize("text,intent", [
    ("yes that works", "yes"), ("No, something else", "no"), ("how about Saturday", "pick"),
    ("evening is better", "pick"), ("could you say that again", "repeat"), ("please stop", "end"), ("banana", "unknown")])
def test_understanding(text, intent):
    assert understand(text)[0] == intent


def test_call_opens_with_the_checked_slot_and_is_recorded_not_dialled():
    c, client = make()
    call = start(client, incident(client, c))
    assert call["simulated"] and call["status"] == "in_progress" and call["to_masked"].endswith("23")
    assert "Wednesday" in call["transcript"][0]["text"] and "M. Nguyen" in call["transcript"][0]["text"]
    kinds = [e["kind"] for e in client.get(f"/api/incidents/{c.store.incidents and next(iter(c.store.incidents))}").json()["activity"]]
    assert "call_started" in kinds


def test_accepting_with_autopilot_off_keeps_the_slot_held_until_approval():
    c, client = make()
    iid = incident(client, c)
    call = start(client, iid)
    done = say(client, call["id"], "yes, that works")
    assert done["outcome"] == "accepted" and done["status"] == "completed" and not done["confirmed"]
    b = booking(client, iid)
    assert b["status"] == "tentative"
    assert client.post(f"/api/calendar/bookings/{b['id']}/confirm").status_code == 409  # still gated


def test_accepting_with_autopilot_on_confirms_the_slot_but_not_the_work_order():
    c, client = make()
    client.put("/api/autonomy", json={"level": "autopilot"})
    iid = incident(client, c)
    calls = client.get("/api/calendar/calls", params={"incident_id": iid}).json()
    assert len(calls) == 1  # Autopilot placed the call itself, once
    done = say(client, calls[0]["id"], "sounds good")
    assert done["confirmed"] and booking(client, iid)["status"] == "confirmed"
    v = client.get(f"/api/incidents/{iid}").json()
    wo = next(a for a in v["actions"] if a["kind"] == "dispatch_work_order")
    assert wo["status"] == "awaiting_approval"  # lockout/tagout sign-off still belongs to a person
    assert any(e["actor"] == "policy" and e["kind"] in ("schedule_confirmed", "call_accepted") for e in v["activity"])
    seek(client, CRAH, 230)
    assert len(client.get("/api/calendar/calls", params={"incident_id": iid}).json()) == 1  # no second call


def test_a_weekday_picks_another_checked_slot_and_books_it():
    c, client = make()
    iid = incident(client, c, free_deadline=True)
    call = start(client, iid)
    assert len(call["options"]) >= 2
    r = say(client, call["id"], "Saturday would be better")
    assert r["status"] == "in_progress" and "Saturday" in r["transcript"][-1]["text"]
    done = say(client, call["id"], "yes")
    assert done["outcome"] == "accepted" and "Saturday" in done["accepted_text"]
    assert booking(client, iid)["start"].startswith("2026-10-24")


def test_declining_every_slot_ends_the_call_and_leaves_the_hold():
    c, client = make()
    iid = incident(client, c)
    call = start(client, iid)
    held = booking(client, iid)["start"]
    done = say(client, call["id"], "no")
    assert done["outcome"] == "declined" and booking(client, iid)["start"] == held


def test_two_silent_turns_end_the_call():
    c, client = make()
    call = start(client, incident(client, c))
    say(client, call["id"], "")
    assert say(client, call["id"], "  ")["outcome"] == "silent"


def test_no_slot_or_no_phone_is_refused():
    c = build_container(make_settings())
    client = TestClient(create_app(c))
    iid = seek(client, CRAH, 216)["triggered_incident_id"]
    r = client.post("/api/calendar/call", json={"incident_id": iid})
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_phone"


def test_real_calls_use_signed_webhooks_and_a_live_provider():
    c, client = make(mode="auto", twilio_account_sid="AC1", twilio_auth_token="tok", call_from_number="+15125550000")
    placed = []

    def handler(req: httpx.Request):
        placed.append(req.content.decode())
        return httpx.Response(201, json={"sid": "CA1"})

    c.calls.provider = TwilioCalls(account_sid="AC1", auth_token="tok", from_number="+15125550000",
                                   transport=httpx.MockTransport(handler))
    iid = incident(client, c)
    call = start(client, iid)
    assert not call["simulated"] and call["status"] == "queued" and placed and "twiml" in placed[0]
    assert client.post(f"/api/voice/calls/{call['id']}/say", json={"text": "yes"}).status_code == 409  # real: no typing

    base = c.settings.public_base_url.rstrip("/")
    url = f"{base}/api/voice/calls/{call['id']}/turn"
    params = {"SpeechResult": "yes please", "CallSid": "CA1"}
    bad = client.post(f"/api/voice/calls/{call['id']}/turn", data=params, headers={"X-Twilio-Signature": "nope"})
    assert bad.status_code == 403
    ok = client.post(f"/api/voice/calls/{call['id']}/turn", data=params,
                     headers={"X-Twilio-Signature": twilio_signature("tok", url, params)})
    assert ok.status_code == 200 and "<Hangup/>" in ok.text and "Wednesday" in ok.text
    assert client.get("/api/calendar/calls").json()[0]["outcome"] == "accepted"


def test_unanswered_call_is_reported_as_failed():
    c, client = make(mode="auto", twilio_account_sid="AC1", twilio_auth_token="tok", call_from_number="+15125550000")
    c.calls.provider = TwilioCalls(account_sid="AC1", auth_token="tok", from_number="+15125550000",
                                   transport=httpx.MockTransport(lambda r: httpx.Response(201, json={"sid": "CA9"})))
    call = start(client, incident(client, c))
    url = f"{c.settings.public_base_url.rstrip('/')}/api/voice/calls/{call['id']}/status"
    params = {"CallStatus": "no-answer"}
    r = client.post(f"/api/voice/calls/{call['id']}/status", data=params, headers={"X-Twilio-Signature": twilio_signature("tok", url, params)})
    assert r.status_code == 204 and client.get("/api/calendar/calls").json()[0]["status"] == "failed"


def tight_deadline(container, iid):
    inc = container.store.incidents[iid]
    rul = inc.prognostics.rul.model_copy(update={"lower_hours": 1.0})
    container.store.incidents[iid] = inc.model_copy(update={"prognostics": inc.prognostics.model_copy(update={"rul": rul})})
    container.calendar.sync_incident(iid)


def test_when_nothing_fits_the_call_still_happens_with_a_provisional_date():
    c, client = make()
    client.put("/api/autonomy", json={"level": "autopilot"})
    iid = incident(client, c)
    for call in client.get("/api/calendar/calls", params={"incident_id": iid}).json():  # drop Autopilot's own first call
        say(client, call["id"], "stop")
    tight_deadline(c, iid)
    call = start(client, iid)
    text = call["transcript"][0]["text"]
    assert "provisional date" in text and "Operations will confirm" in text
    done = say(client, call["id"], "yes")
    assert done["outcome"] == "accepted" and not done["confirmed"]  # never confirmed, even on Autopilot
    v = client.get(f"/api/incidents/{iid}").json()
    assert any(e["kind"] == "call_provisional" for e in v["activity"])
    assert any(e["kind"] == "call_accepted" and "provisional" in e["text"] for e in v["activity"])


def test_emergency_stop_on_a_machine_with_no_fitting_slot_still_calls():
    c = build_container(make_settings(scheduler_call_phone=PHONE))
    client = TestClient(create_app(c))
    r = client.post(f"/api/machines/CH-02/emergency-stop").json()
    assert r["call"] and r["call"]["status"] == "in_progress"
