"""Scheduling: constraints, N+1, no-fit warning, holds and approval gating."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ghostshift.schemas.ops import FixtureBooking

from .conftest import CRAH, seek
from .test_ops_inventory import actions, approve, open_incident, send_order

AS_OF = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
SKILLS = ["Critical facilities technician", "Electrical (qualified)"]


def propose(container, **kw):
    args = dict(machine_id=CRAH, duration_h=3.0, skills=SKILLS, as_of=AS_OF, part_ready=None, deadline=None)
    args.update(kw)
    return container.calendar.propose(**args)


def dt(day, hour):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


# --------------------------------------------------------------- the rules
def test_picks_earliest_window_with_an_on_shift_skilled_technician(container):
    p = propose(container)
    assert p.status == "fits"
    assert (p.chosen.start, p.chosen.technician_name) == (dt(21, 22), "M. Nguyen")  # only electrical tech on nights
    assert p.chosen.end == dt(22, 1)
    assert any("N+1" in r for r in p.rationale)
    assert [a.feasible for a in p.alternatives] == [False, False] or all(a.window_label for a in p.alternatives)


def test_slot_must_come_after_the_part_arrives(container):
    p = propose(container, part_ready=dt(22, 12))
    first = next(a for a in p.alternatives if a.window_start == dt(21, 22))
    assert not first.feasible and "part does not arrive" in first.reasons[0]
    assert p.chosen.window_start == dt(24, 14)


def test_slot_must_finish_before_the_earliest_limit(container):
    p = propose(container, deadline=dt(22, 0))  # window 1 would end 01:00
    assert p.status == "no_fit"
    assert all("after the earliest estimated limit" in " ".join(a.reasons) for a in p.alternatives[:2])
    assert "Operations needs to decide" in p.warnings[0]


def test_deadline_only_allows_a_slot_that_finishes_in_time(container):
    p = propose(container, deadline=dt(22, 2))
    assert p.chosen.end <= dt(22, 2) and p.chosen.start == dt(21, 22)


def test_missing_skills_means_no_fit_with_a_reason(container):
    p = propose(container, duration_h=6.0, skills=[*SKILLS, "Refrigeration (qualified)"])  # only D. Okafor, on days
    assert p.status == "no_fit"
    assert any("not on shift" in r for a in p.alternatives for r in a.reasons)


def test_technician_without_the_skill_is_never_assigned(container):
    p = propose(container, skills=SKILLS, part_ready=dt(26, 0))
    assert p.chosen is None or p.chosen.technician_name != "S. Patel"
    assert container.calendar.check_slot(CRAH, dt(26, 15), 2, SKILLS, technician_id="T-PAT")[0] is None


def test_busy_technician_is_skipped_for_a_free_one(container):
    # Saturday 14:00: R. Alvarez is on a UPS inspection (and off shift); J. Brooks takes it.
    p = propose(container, part_ready=dt(24, 0))
    assert p.chosen.window_start == dt(24, 14) and p.chosen.technician_name == "J. Brooks"
    container.calendar.fixture_bookings.append(FixtureBooking(
        id="X", title="Row C audit", machine_id=None, technician_id="T-BRK", start=dt(24, 14), end=dt(24, 18)))
    p = propose(container, part_ready=dt(24, 0))
    assert p.chosen.start == dt(24, 18) and p.chosen.technician_name == "J. Brooks"  # waits until Brooks is free


def test_n_plus_one_blocks_maintenance_on_the_partner_unit(container):
    container.calendar.fixture_bookings.append(FixtureBooking(
        id="MF08", title="MF-08 PSU swap", machine_id="MF-08", technician_id=None, start=dt(21, 20), end=dt(22, 7)))
    p = propose(container)
    first = next(a for a in p.alternatives if a.window_start == dt(21, 22))
    assert not first.feasible and any("N+1" in r and "MF-08" in r for r in first.reasons)
    assert p.chosen.window_start != dt(21, 22)


def test_n_plus_one_applies_to_chillers_too(container):
    tech, reasons, _ = container.calendar.check_slot(
        "CH-02", dt(25, 8), 2, ["Refrigeration (qualified)"])  # CH-03 refrigerant check is booked 08:00 to 11:00
    assert tech is None and any("N+1" in r and "CH-03" in r for r in reasons)


def test_holds_count_as_busy_for_the_next_work_order(client, container):
    iid = open_incident(client)
    hold = container.calendar.bookings(incident_id=iid)[0]
    again = propose(container, as_of=AS_OF)
    assert again.chosen.start != hold.start or again.chosen.technician_id != hold.technician_id


# ---------------------------------------------------------- hold lifecycle
def test_hold_is_created_with_the_work_order_and_stays_tentative(client):
    iid = open_incident(client)
    b = client.get("/api/calendar/bookings", params={"incident_id": iid}).json()
    assert len(b) == 1 and b[0]["status"] == "tentative" and b[0]["technician_name"] == "M. Nguyen"
    v = client.get(f"/api/incidents/{iid}").json()
    assert v["work_order"]["window_start"] == b[0]["start"]
    kinds = [e["kind"] for e in v["activity"]]
    assert "schedule_hold" in kinds and "schedule_confirmed" not in kinds


def test_confirm_is_refused_until_the_work_order_is_approved(client):
    iid = open_incident(client)
    b = client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]
    r = client.post(f"/api/calendar/bookings/{b['id']}/confirm")
    assert r.status_code == 409 and r.json()["error"]["code"] == "approval_required"
    acts, _ = actions(client, iid)
    approve(client, acts["dispatch_work_order"], attest=True)
    after = client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]
    assert after["status"] == "confirmed"
    assert "schedule_confirmed" in [e["kind"] for e in client.get(f"/api/incidents/{iid}").json()["activity"]]


def test_rejecting_the_work_order_does_not_confirm_the_slot(client):
    iid = open_incident(client)
    acts, _ = actions(client, iid)
    client.post(f"/api/actions/{acts['dispatch_work_order']['id']}/decision", json={
        "role": "maintenance_supervisor", "approver_name": "T", "decision": "reject"})
    assert client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]["status"] == "tentative"


def test_autopilot_orders_parts_but_never_confirms_the_slot(client):
    client.put("/api/autonomy", json={"level": "autopilot"})
    iid = open_incident(client)
    assert client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]["status"] == "tentative"


def test_late_part_moves_the_hold_or_warns_when_nothing_fits(client, container):
    container.inventory._stock["GS-BRG-FAN-KIT"]["on_hand"] = 0
    iid = open_incident(client)
    send_order(client, iid)  # supplier order arrives Thu 12:00, after the Wednesday window and before no other window
    assert client.get("/api/calendar/bookings", params={"incident_id": iid}).json() == []
    texts = [e for e in client.get(f"/api/incidents/{iid}").json()["activity"]]
    assert any(e["kind"] == "schedule_released" for e in texts)
    assert any(e["kind"] == "schedule_warning" and "Operations needs to decide" in e["text"] for e in texts)


def test_reschedule_checks_the_rules_and_cancel_releases_it(client):
    iid = open_incident(client)
    b = client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]
    bad = client.post(f"/api/calendar/bookings/{b['id']}/reschedule", json={"start": "2026-10-22T10:00:00Z"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "slot_not_allowed"
    assert any("maintenance window" in r for r in bad.json()["error"]["details"]["reasons"])
    ok = client.post(f"/api/calendar/bookings/{b['id']}/reschedule", json={"start": "2026-10-21T23:00:00Z"})
    assert ok.status_code == 200 and ok.json()["start"].startswith("2026-10-21T23:00")
    gone = client.post(f"/api/calendar/bookings/{b['id']}/cancel").json()
    assert gone["status"] == "cancelled"
    assert client.get("/api/calendar/bookings", params={"incident_id": iid}).json() == []
    assert client.post(f"/api/calendar/bookings/{b['id']}/confirm").status_code == 409


def test_propose_and_hold_endpoints(client):
    iid = open_incident(client)
    wo = client.get(f"/api/incidents/{iid}").json()["work_order"]["id"]
    p = client.post("/api/calendar/propose", json={"work_order_id": wo}).json()
    assert p["status"] == "fits" and p["chosen"]["technician_name"] == "M. Nguyen" and p["alternatives"]
    assert client.post("/api/calendar/holds", json={"work_order_id": wo}).status_code == 201
    assert len(client.get("/api/calendar/bookings").json()) == 1
    assert client.post("/api/calendar/propose", json={"work_order_id": "WO-9999"}).status_code == 404


def test_events_list_windows_jobs_and_holds_and_ics(client):
    iid = open_incident(client)
    ev = client.get("/api/calendar/events", params={"start": "2026-10-19T00:00:00Z", "end": "2026-10-29T00:00:00Z"}).json()
    kinds = {e["kind"] for e in ev["events"]}
    assert {"maintenance_window", "existing_job", "ghostshift_hold"} <= kinds
    assert ev["technicians"] and ev["shifts"] and ev["redundancy"]
    b = client.get("/api/calendar/bookings", params={"incident_id": iid}).json()[0]
    ics = client.get(f"/api/calendar/bookings/{b['id']}/ics")
    assert ics.status_code == 200 and "BEGIN:VEVENT" in ics.text and "STATUS:TENTATIVE" in ics.text


def test_phone_plan_endpoint_needs_a_valid_link(client):
    iid = open_incident(client)
    url = client.get(f"/api/incidents/{iid}").json()["notifications"][0]["inspection_url"]
    token = url.split("/m/")[1]
    plan = client.get(f"/api/inspect/{token}/plan").json()
    assert plan["booking"]["technician_name"] == "M. Nguyen"
    assert client.get("/api/inspect/not-a-token/plan").status_code == 404


def test_reset_clears_bookings(client):
    open_incident(client)
    client.post("/api/demo/reset")
    assert client.get("/api/calendar/bookings").json() == []
