"""Tests for Workstream 3: Multimodal Synthetic Telemetry Provider and Streaming SSE routes."""

from __future__ import annotations

import json
from fastapi.testclient import TestClient

from ghostshift.container import build_container
from ghostshift.integrations.base import TelemetryProvider
from ghostshift.integrations.multimodal_stream import MultimodalStreamAdapter
from ghostshift.main import create_app
from ghostshift.schemas.common import Severity
from ghostshift.schemas.telemetry import Anchor3D, MultimodalTick

from .conftest import make_settings, VMC


def test_multimodal_adapter_satisfies_protocol():
    adapter = MultimodalStreamAdapter()
    assert isinstance(adapter, TelemetryProvider)
    assert adapter.machine_ids() == ["VMC-07-MULTIMODAL", "AI4I-MULTIMODAL"]
    assert adapter.length("VMC-07-MULTIMODAL") == 240

    h = adapter.health()
    assert h.configured is True and h.available is True
    assert h.capability == "telemetry"

    win = adapter.window("VMC-07-MULTIMODAL", 0, 10)
    assert win.machine_id == "VMC-07-MULTIMODAL"
    assert len(win.points) == 11
    assert "acoustic_db" in win.points[0].values
    assert "thermal_max_c" in win.points[0].values
    assert "swarf_discoloration" in win.points[0].values


def test_multimodal_phases_and_anchors():
    adapter = MultimodalStreamAdapter()

    # Phase 1: Nominal
    tick0 = adapter.stream_tick("VMC-07-MULTIMODAL", 0)
    assert isinstance(tick0, MultimodalTick)
    assert tick0.phase == "nominal"
    assert tick0.severity == Severity.normal
    assert tick0.anchor_3d.component == "Spindle Centerline"
    assert tick0.values["acoustic_db"] < 70.0
    assert tick0.values["thermal_max_c"] < 45.0
    assert tick0.values["swarf_discoloration"] < 0.05

    # Phase 2: Incipient Bearing Chatter
    tick100 = adapter.stream_tick("VMC-07-MULTIMODAL", 100)
    assert tick100.phase == "incipient_chatter"
    assert tick100.severity == Severity.warning
    assert tick100.anchor_3d.component == "Spindle Bearing B"
    assert tick100.values["acoustic_db"] > 70.0

    # Phase 3: Critical Thermal Breakdown
    tick160 = adapter.stream_tick("VMC-07-MULTIMODAL", 160)
    assert tick160.phase == "critical_heating"
    assert tick160.severity == Severity.critical
    assert tick160.anchor_3d.component == "Spindle Bearing B"
    assert tick160.values["thermal_max_c"] > 60.0
    assert tick160.values["swarf_discoloration"] > 0.15

    # Phase 4: Extreme Tool Wear Stall Risk
    tick220 = adapter.stream_tick("VMC-07-MULTIMODAL", 220)
    assert tick220.phase == "tool_wear_stall"
    assert tick220.severity == Severity.critical
    assert tick220.anchor_3d.component == "Cutting Tool Holder"
    assert tick220.values["tool_wear"] > 200.0


def test_multimodal_container_registration():
    s = make_settings(mode="demo")
    c = build_container(s, enable_multimodal=True)
    mids = c.telemetry.machine_ids()
    assert "VMC-07-MULTIMODAL" in mids
    assert "AI4I-MULTIMODAL" in mids
    assert "VMC-07-MULTIMODAL" in c.reference.machines

    app = create_app(c)
    client = TestClient(app)
    machines = client.get("/api/machines").json()
    returned_ids = {m["id"] for m in machines}
    assert "VMC-07-MULTIMODAL" in returned_ids
    assert "AI4I-MULTIMODAL" in returned_ids


def test_multimodal_streaming_sse_endpoint():
    s = make_settings(mode="demo")
    c = build_container(s, enable_multimodal=True)
    client = TestClient(create_app(c))

    with client.stream("GET", f"/api/machines/{VMC}/stream?speed=100.0&loop=false") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 4:
                break
        assert any(l.startswith("event: telemetry") for l in lines)
        data_lines = [l for l in lines if l.startswith("data: ")]
        assert len(data_lines) > 0
        payload = json.loads(data_lines[0].replace("data: ", ""))
        assert "values" in payload
        assert "anchor_3d" in payload


def test_multimodal_streaming_default_route():
    s = make_settings(mode="demo")
    c = build_container(s, enable_multimodal=True)
    client = TestClient(create_app(c))

    with client.stream("GET", f"/api/telemetry/stream?machine_id={VMC}&speed=100.0&loop=false") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
