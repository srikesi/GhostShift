"""Each stub and each real-provider boundary, with network mocked."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from faultzy.config import ExecutionMode
from faultzy.container import build_container, choose_llm, choose_sms, choose_voice
from faultzy.integrations.ai4i import AI4IDatasetAdapter
from faultzy.integrations.base import ProviderError, ProviderNotConfigured
from faultzy.integrations.bedrock import BedrockConverseLLM
from faultzy.integrations.sms import SimulatedSms, TwilioSms
from faultzy.integrations.supply import SimulatedProcurement, SimulatedWorkOrders
from faultzy.integrations.voice import ElevenLabsVoice, TextOnlyVoice
from faultzy.schemas.agents import DiagnosticsInput

from .conftest import make_settings

SAMPLE_AI4I = Path(__file__).parent / "data" / "ai4i_format_sample.csv"


# ---------------------------------------------------------------- selection
def test_demo_mode_never_selects_real_providers():
    s = make_settings(mode="demo", sms_provider="twilio", voice_provider="elevenlabs", bedrock_model_id="x",
                      TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t", TWILIO_FROM_NUMBER="+1")
    assert choose_llm(s) is None
    assert isinstance(choose_sms(s), SimulatedSms)
    assert isinstance(choose_voice(s), TextOnlyVoice)


def test_auto_mode_selects_real_only_when_configured():
    assert choose_llm(make_settings(mode="auto")) is None
    assert isinstance(choose_llm(make_settings(mode="auto", bedrock_model_id="m")), BedrockConverseLLM)
    assert isinstance(choose_sms(make_settings(mode="auto", sms_provider="twilio")), SimulatedSms)
    s = make_settings(mode="auto", sms_provider="twilio", TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t",
                      TWILIO_FROM_NUMBER="+15550000000")
    assert isinstance(choose_sms(s), TwilioSms)


def test_aws_mode_selects_real_even_if_unconfigured():
    s = make_settings(mode="aws", sms_provider="twilio")
    assert s.mode == ExecutionMode.aws
    assert isinstance(choose_llm(s), BedrockConverseLLM)
    assert isinstance(choose_sms(s), TwilioSms)


# ------------------------------------------------------------------ Bedrock
class FakeBedrockClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def converse(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def test_bedrock_converse_request_and_parse():
    client = FakeBedrockClient({"output": {"message": {"content": [{"text": '{"a": 1}'}]}},
                                "usage": {"inputTokens": 10, "outputTokens": 5}})
    llm = BedrockConverseLLM(model_id="us.example.model-v1", region="us-west-2", client_factory=lambda r, t: client)
    r = llm.complete("sys", "hi", max_tokens=50)
    assert r.text == '{"a": 1}' and r.input_tokens == 10
    assert client.kwargs["modelId"] == "us.example.model-v1"
    assert client.kwargs["system"] == [{"text": "sys"}]
    assert client.kwargs["inferenceConfig"]["maxTokens"] == 50


def test_bedrock_without_model_id_is_not_configured_and_makes_no_client():
    created = []
    llm = BedrockConverseLLM(model_id=None, region="us-east-1", client_factory=lambda r, t: created.append(1))
    with pytest.raises(ProviderNotConfigured):
        llm.complete("s", "p")
    assert created == [] and llm.health().configured is False


def test_bedrock_client_errors_are_classified():
    from botocore.exceptions import ClientError, NoCredentialsError

    def err(code):
        return ClientError({"Error": {"Code": code, "Message": "m"}}, "Converse")

    for code, retryable in [("ThrottlingException", True), ("AccessDeniedException", False), ("ValidationException", False)]:
        llm = BedrockConverseLLM(model_id="m", region="r", client_factory=lambda r, t, c=code: FakeBedrockClient(error=err(c)))
        with pytest.raises(ProviderError) as exc:
            llm.complete("s", "p")
        assert exc.value.retryable is retryable and code in str(exc.value)
    llm = BedrockConverseLLM(model_id="m", region="r", client_factory=lambda r, t: FakeBedrockClient(error=NoCredentialsError()))
    with pytest.raises(ProviderNotConfigured):
        llm.complete("s", "p")


def test_bedrock_health_does_not_probe_by_default():
    calls = []
    llm = BedrockConverseLLM(model_id="m", region="r", client_factory=lambda r, t: calls.append(1))
    h = llm.health()
    assert h.configured and h.available is None and calls == []


# ------------------------------------------------------------------- Twilio
def twilio(handler, override_to="+15125550100", **kw):
    return TwilioSms(account_sid="AC123", auth_token="secret", from_number="+15125550000", override_to=override_to,
                     transport=httpx.MockTransport(handler), sleep=lambda _: None, **kw)


def test_twilio_success_sends_only_to_override_number():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = req.content.decode()
        seen["url"] = str(req.url)
        return httpx.Response(201, json={"sid": "SM123"})

    r = twilio(handler).send(to="+15125550142", body="hello")
    assert r.delivered and not r.simulated and r.external_id == "SM123"
    assert "To=%2B15125550100" in seen["body"] and "15125550142" not in seen["body"]
    assert "/Accounts/AC123/Messages.json" in seen["url"]


def test_twilio_retries_5xx_with_bound():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(503, json={"code": 20503, "message": "unavailable"})

    r = twilio(handler, max_attempts=3).send(to="x", body="b")
    assert not r.delivered and r.attempts == 3 and len(calls) == 3 and "503" in r.error


def test_twilio_does_not_retry_4xx():
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(400, json={"code": 21211, "message": "Invalid 'To' Phone Number"})

    r = twilio(handler).send(to="x", body="b")
    assert not r.delivered and len(calls) == 1 and "21211" in r.error


def test_twilio_skips_without_explicit_recipient_and_reports_unconfigured():
    r = twilio(lambda req: httpx.Response(201, json={}), override_to=None).send(to="x", body="b")
    assert r.skipped and not r.delivered
    r = TwilioSms(account_sid=None, auth_token=None, from_number=None, override_to=None).send(to="x", body="b")
    assert not r.delivered and "not configured" in r.error


def test_simulated_sms_records_message():
    s = SimulatedSms()
    r = s.send(to="+1", body="b")
    assert r.delivered and r.simulated and s.outbox == [{"to": "+1", "body": "b"}]


# --------------------------------------------------------------- ElevenLabs
def test_elevenlabs_success_and_failure():
    ok = ElevenLabsVoice(api_key="k", voice_id="v", model_id="m",
                         transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"ID3audio")))
    r = ok.synthesize("hello")
    assert r.audio == b"ID3audio" and r.mime_type == "audio/mpeg"
    bad = ElevenLabsVoice(api_key="k", voice_id="v", model_id="m",
                          transport=httpx.MockTransport(lambda req: httpx.Response(401, text="unauthorized")))
    r = bad.synthesize("hello")
    assert r.audio is None and "401" in r.error
    assert ElevenLabsVoice(api_key=None, voice_id=None, model_id="m").synthesize("x").error


def test_text_only_voice():
    r = TextOnlyVoice().synthesize("hello")
    assert r.audio is None and r.simulated and r.error is None


# ------------------------------------------------------- procurement / CMMS
def test_simulated_procurement_and_work_orders():
    p = SimulatedProcurement().submit_requisition(requisition_id="REQ-1", sku="X", quantity=1)
    w = SimulatedWorkOrders().dispatch(work_order_id="WO-1", title="t", machine_id="M")
    assert p.simulated and p.external_reference.startswith("SIM-PR-")
    assert w.simulated and w.external_reference.startswith("SIM-WO-")


# --------------------------------------------------------------------- AI4I
def test_ai4i_adapter_normalizes_and_documents_gaps():
    a = AI4IDatasetAdapter(SAMPLE_AI4I)
    w = a.window("AI4I-MILL", 0, 9)
    assert len(w.points) == 10
    assert set(w.sensor_ids) == {"air_temp", "process_temp", "rotational_speed", "torque", "tool_wear"}
    assert abs(w.points[0].values["air_temp"] - (298.1 - 273.15)) < 1e-6  # K -> °C
    assert w.provenance.source.value == "measured"
    assert w.timestamp_provenance.source.value == "simulated"
    assert any("vibration" in f for f in w.unavailable_fields)
    assert "Machine failure" in a.labels()[0]
    assert all("Machine failure" not in p.values for p in w.points)  # labels never reach agents


def test_ai4i_machine_runs_through_diagnostics():
    c = build_container(make_settings(), ai4i_path=SAMPLE_AI4I)
    assert "AI4I-MILL" in c.telemetry.machine_ids()
    o = c.orchestrator
    w = o.window("AI4I-MILL", c.telemetry.length("AI4I-MILL") - 1)
    sc = c.reference.scenarios["AI4I-MILL"]
    d = o.diagnostics.run(DiagnosticsInput(machine=c.reference.machine("AI4I-MILL"), window=w,
                                           baseline_start_index=sc.baseline_start_index,
                                           baseline_end_index=sc.baseline_end_index))
    assert any("Unavailable from source" in x for x in d.warnings)
    run = o.run("AI4I-MILL")
    assert run.status.value in {"completed_no_incident", "completed", "awaiting_approval"}


def test_ai4i_rejects_wrong_schema(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="Not an AI4I"):
        AI4IDatasetAdapter(bad).length("AI4I-MILL")
