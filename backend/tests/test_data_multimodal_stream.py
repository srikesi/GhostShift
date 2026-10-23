"""Tests for Workstream 3: Multimodal Synthetic Telemetry Provider, Fault Injection and Streaming SSE routes."""

from __future__ import annotations

import json
from fastapi.testclient import TestClient

from ghostshift.container import build_container
from ghostshift.integrations.base import TelemetryProvider
from ghostshift.integrations.multimodal_stream import MultimodalStreamAdapter
from ghostshift.main import create_app
from ghostshift.schemas.common import Severity
from ghostshift.schemas.telemetry import Anchor3D, MultimodalTick

from .conftest import make_settings, CRAH


def test_multimodal_adapter_satisfies_protocol():
    adapter = MultimodalStreamAdapter()
    assert isinstance(adapter, TelemetryProvider)
    assert "CRAH-07-MULTIMODAL" in adapter.machine_ids()
    assert adapter.length("CRAH-07-MULTIMODAL") == 240

    h = adapter.health()
    assert h.configured is True and h.available is True
    assert h.capability == "telemetry"

    win = adapter.window("CRAH-07-MULTIMODAL", 0, 10)
    assert win.machine_id == "CRAH-07-MULTIMODAL"
    assert len(win.points) == 11
    assert "acoustic_db" in win.points[0].values
    assert "thermal_max_c" in win.points[0].values
    assert "spindle_motor_current" in win.points[0].values


def test_multimodal_phases_and_anchors():
    adapter = MultimodalStreamAdapter()

    # Phase 1: Nominal
    tick0 = adapter.stream_tick("CRAH-07-MULTIMODAL", 0)
    assert isinstance(tick0, MultimodalTick)
    assert tick0.phase == "nominal"
    assert tick0.severity == Severity.normal
    assert "Centerline" in tick0.anchor_3d.component
    assert tick0.values["acoustic_db"] < 70.0
    assert tick0.values["thermal_max_c"] < 45.0

    # Phase 2: Incipient Bearing Chatter
    tick100 = adapter.stream_tick("CRAH-07-MULTIMODAL", 100)
    assert tick100.phase == "incipient_chatter"
    assert tick100.severity == Severity.warning
    assert "Bearing" in tick100.anchor_3d.component
    assert tick100.values["acoustic_db"] > 70.0

    # Phase 3: Critical Thermal Breakdown
    tick160 = adapter.stream_tick("CRAH-07-MULTIMODAL", 160)
    assert tick160.phase == "critical_heating"
    assert tick160.severity == Severity.critical
    assert "Bearing" in tick160.anchor_3d.component
    assert tick160.values["thermal_max_c"] > 60.0

    # Phase 4: Extreme Stall Risk
    tick220 = adapter.stream_tick("CRAH-07-MULTIMODAL", 220)
    assert tick220.phase == "tool_wear_stall"
    assert tick220.severity == Severity.critical
    assert "Impeller" in tick220.anchor_3d.component


def test_interactive_fault_injection_and_estop():
    adapter = MultimodalStreamAdapter()

    # Inject Mild Anomaly
    res_mild = adapter.inject_fault("CRAH-07-MULTIMODAL", "mild")
    assert res_mild["status"] == "injected"
    tick_mild = adapter.stream_tick("CRAH-07-MULTIMODAL", 10)
    assert tick_mild.phase == "incipient_flutter"
    assert tick_mild.severity == Severity.warning
    assert tick_mild.values["spindle_vib_rms"] > 2.8

    # Inject Critical Breakdown
    res_crit = adapter.inject_fault("CRAH-07-MULTIMODAL", "critical")
    assert res_crit["status"] == "injected"
    tick_crit = adapter.stream_tick("CRAH-07-MULTIMODAL", 15)
    assert tick_crit.phase == "catastrophic_breakdown"
    assert tick_crit.severity == Severity.critical
    assert tick_crit.values["thermal_max_c"] > 85.0

    # Trigger Autonomous E-STOP
    res_estop = adapter.emergency_stop("CRAH-07-MULTIMODAL")
    assert res_estop["status"] == "estop_executed"
    tick_estop = adapter.stream_tick("CRAH-07-MULTIMODAL", 20)
    assert tick_estop.phase == "emergency_shutdown_loto_active"
    assert tick_estop.values["spindle_motor_current"] == 0.0
    assert tick_estop.values["rotational_speed"] < 500.0  # Decaying
    assert "LOTO" in tick_estop.anchor_3d.component

    # Reset
    adapter.reset_fault("CRAH-07-MULTIMODAL")
    tick_norm = adapter.stream_tick("CRAH-07-MULTIMODAL", 0)
    assert tick_norm.phase == "nominal"


def test_multimodal_container_registration():
    s = make_settings(mode="demo")
    c = build_container(s, enable_multimodal=True)
    mids = c.telemetry.machine_ids()
    assert "CRAH-07-MULTIMODAL" in mids
    assert "CRAH-07-MULTIMODAL" in c.reference.machines

    app = create_app(c)
    client = TestClient(app)
    machines = client.get("/api/machines").json()
    returned_ids = {m["id"] for m in machines}
    assert "CRAH-07-MULTIMODAL" in returned_ids


def test_fault_injection_and_streaming_api_routes():
    s = make_settings(mode="demo")
    c = build_container(s, enable_multimodal=True)
    client = TestClient(create_app(c))

    # Test POST /api/machines/{machine_id}/inject-fault
    r_mild = client.post(f"/api/machines/{CRAH}/inject-fault", json={"fault_type": "mild"})
    assert r_mild.status_code == 200
    assert r_mild.json()["fault_type"] == "mild"
    assert "WARNING" in r_mild.json()["sms_sent"]

    # Test POST /api/machines/{machine_id}/emergency-stop
    r_estop = client.post(f"/api/machines/{CRAH}/emergency-stop")
    assert r_estop.status_code == 200
    assert r_estop.json()["status"] == "estop_active"
    assert r_estop.json()["current_a"] == 0.0

    # Test GET streaming SSE endpoint
    with client.stream("GET", f"/api/machines/{CRAH}/stream?speed=100.0&loop=false") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 4:
                break
        assert any(l.startswith("event: telemetry") for l in lines)
