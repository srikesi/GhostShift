from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ghostshift.config import Settings
from ghostshift.container import build_container
from ghostshift.integrations.base import LlmResponse, ProviderHealth
from ghostshift.main import create_app
from ghostshift.schemas.common import ProviderInfo, ProviderKind

CRAH, CH = "MF-07", "CH-02"


def make_settings(**kw) -> Settings:
    kw.setdefault("mode", "demo")
    return Settings(_env_file=None, **kw)


@pytest.fixture
def container():
    return build_container(make_settings())


@pytest.fixture
def client(container):
    return TestClient(create_app(container))


class FakeLLM:
    """Scripted LLM. Each reply is a string (returned) or an exception (raised)."""

    info = ProviderInfo(name="fake-llm", kind=ProviderKind.external, real=True, model_id="fake-model")

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system, prompt, *, max_tokens=700):
        r = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        if isinstance(r, BaseException):
            raise r
        if callable(r):
            return r()
        return LlmResponse(text=r, model_id="fake-model", latency_ms=1.0)

    def health(self, probe=False):
        return ProviderHealth(capability="llm", provider=self.info, configured=True, available=True, detail="fake")


VALID_NARRATIVE = (
    '{"headline": "MF-07 fan bearing wear detected", '
    '"summary": "Fan vibration has risen well above baseline and crossed the alert limit.", '
    '"technician_brief": "Check fan bearing; isolate per site LOTO before work.", '
    '"sms_key_finding": "Fan vibration above alert limit"}'
)


def seek(client, machine_id, cursor):
    r = client.post(f"/api/machines/{machine_id}/replay", json={"action": "seek", "cursor": cursor})
    assert r.status_code == 200, r.text
    return r.json()
