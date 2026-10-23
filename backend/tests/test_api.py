from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from ghostshift.container import build_container
from ghostshift.main import create_app
from ghostshift.schemas.common import utcnow

from .conftest import CH, CRAH, make_settings, seek


def test_health_reports_mode_and_providers(client):
    body = client.get("/api/health").json()
    assert body["app"] == "GhostShift" and body["mode"] == "demo" and body["status"] == "ok"
    caps = {p["capability"] for p in body["providers"]}
    assert {"telemetry", "llm", "parts_catalog", "procurement", "work_orders", "sms", "voice"} <= caps
    assert all(not p["provider"]["real"] for p in body["providers"])


def test_app_starts_in_aws_mode_without_credentials():
    s = make_settings(mode="aws", sms_provider="twilio", voice_provider="elevenlabs")
    c = TestClient(create_app(build_container(s)))
    body = c.get("/api/health").json()
    by_cap = {p["capability"]: p for p in body["providers"]}
    assert by_cap["llm"]["configured"] is False and by_cap["llm"]["provider"]["real"] is True
    assert by_cap["sms"]["configured"] is False
    # Workflow still runs; failures are reported, not masked.
    seek(c, CRAH, 216)
    inc = c.get("/api/incidents").json()[0]
    stages = {s["name"]: s for s in inc["latest_run"]["stages"]}
    assert stages["narrative"]["status"] == "provider_failure"
    assert stages["notification"]["status"] == "provider_failure"
    assert inc["notifications"][0]["status"] == "failed"
    assert inc["incident"]["safety"]["risk_tier"] == "high"


def test_auto_mode_without_credentials_uses_labelled_fallbacks():
    c = TestClient(create_app(build_container(make_settings(mode="auto", sms_provider="twilio"))))
    seek(c, CRAH, 216)
    inc = c.get("/api/incidents").json()[0]
    stages = {s["name"]: s for s in inc["latest_run"]["stages"]}
    assert stages["narrative"]["status"] == "deterministic_fallback"
    assert inc["notifications"][0]["status"] == "simulated_sent"


def test_machines_start_normal(client):
    machines = client.get("/api/machines").json()
    assert {m["id"] for m in machines} == {CRAH, CH}
    assert all(m["status"] == "normal" and m["open_incident_id"] is None for m in machines)


def test_machine_detail_and_unknown_machine(client):
    d = client.get(f"/api/machines/{CRAH}").json()
    assert d["machine"]["drawing"] == "crah"
    assert len(d["component_health"]) == len(d["machine"]["components"])
    r = client.get("/api/machines/NOPE")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_telemetry_separates_labels_from_detection(client):
    t = client.get(f"/api/machines/{CRAH}/telemetry").json()
    assert t["cursor"] == 120 and len(t["window"]["points"]) == 121
    assert t["window"]["provenance"]["source"] == "simulated"
    assert all(p["provenance"]["source"] == "simulated" for p in t["scenario_phases"])
    assert all(seg["severity"] == "normal" for seg in t["detection_segments"])


def test_replay_normal_to_anomalous(client):
    r = client.post(f"/api/machines/{CRAH}/replay", json={"action": "advance", "steps": 4}).json()
    assert r["cursor"] == 124 and r["screening_severity"] == "normal" and r["triggered_run_id"] is None
    r = seek(client, CRAH, 216)
    assert r["screening_severity"] == "warning" and r["triggered_incident_id"]
    m = next(m for m in client.get("/api/machines").json() if m["id"] == CRAH)
    assert m["status"] == "warning" and m["open_incident_id"] == r["triggered_incident_id"]
    t = client.get(f"/api/machines/{CRAH}/telemetry").json()
    assert {s["severity"] for s in t["detection_segments"]} >= {"normal", "watch", "warning"}


def test_replay_reset_closes_incident(client):
    seek(client, CRAH, 216)
    client.post(f"/api/machines/{CRAH}/replay", json={"action": "reset"})
    assert client.get("/api/incidents?status=open").json() == []
    assert client.get(f"/api/machines/{CRAH}").json()["summary"]["replay_cursor"] == 120


def test_invalid_replay_request(client):
    r = client.post(f"/api/machines/{CRAH}/replay", json={"action": "explode"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_manual_workflow_endpoint(client):
    r = client.post(f"/api/machines/{CRAH}/workflow")
    assert r.status_code == 201 and r.json()["status"] == "completed_no_incident"
    run_id = r.json()["id"]
    assert client.get(f"/api/workflows/{run_id}").json()["id"] == run_id
    assert client.get("/api/workflows/RUN-404").status_code == 404


def test_inspection_link_is_scoped_and_expires(client, container):
    r = seek(client, CRAH, 216)
    note = client.get(f"/api/notifications?incident_id={r['triggered_incident_id']}").json()[0]
    token = note["inspection_url"].rsplit("/m/", 1)[1]
    assert len(token) >= 20 and CRAH not in note["inspection_url"].split("/m/")[1]
    view = client.get(f"/api/inspect/{token}").json()
    assert view["incident"]["affected_component_id"] == "fan_bearing"
    assert view["drawing"] == "crah"
    comps = {c["component"]["id"]: c for c in view["components"]}
    assert comps["fan_bearing"]["health"]["status"] == "warning"
    assert comps["chw_valve"]["health"]["status"] == "normal"
    assert view["work_order"]["status"] == "awaiting_approval"
    # Unknown and expired tokens look the same.
    assert client.get("/api/inspect/not-a-token").status_code == 404
    for grant in container.store.grants.values():
        grant.expires_at = utcnow() - timedelta(seconds=1)
    assert client.get(f"/api/inspect/{token}").status_code == 404
    assert token not in str(container.store.grants)  # only hashes are stored


def test_briefing_text_fallback(client):
    r = seek(client, CRAH, 216)
    b = client.get(f"/api/incidents/{r['triggered_incident_id']}/briefing").json()
    assert b["audio_available"] is False and b["audio_url"] is None and len(b["text"]) > 20
    assert client.get(f"/api/incidents/{r['triggered_incident_id']}/briefing/audio").status_code == 404


def test_demo_reset(client):
    seek(client, CRAH, 216)
    assert client.post("/api/demo/reset").status_code == 204
    assert client.get("/api/incidents").json() == []


def test_cors_allows_local_frontend(client):
    r = client.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_serves_built_frontend_when_configured(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>GhostShift</title>")
    (tmp_path / "app.js").write_text("console.log(1)")
    c = TestClient(create_app(build_container(make_settings(static_dir=tmp_path))))
    assert "GhostShift" in c.get("/").text
    assert "GhostShift" in c.get("/m/some-token").text  # client-side route falls back to index.html
    assert c.get("/app.js").text == "console.log(1)"
    assert c.get("/api/health").json()["app"] == "GhostShift"
    assert c.get("/api/nope").status_code == 404
    assert "GhostShift" in c.get("/../../etc/passwd").text  # no path traversal; falls back to index
