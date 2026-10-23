"""GhostMode copilot: Bedrock tool loop (scripted fake client), read-only tools, fallbacks, safety."""

from __future__ import annotations

import json

import pytest

from ghostshift.agents.copilot import MAX_TOOL_CALLS, Copilot, CopilotTools, ToolError, _history_messages
from ghostshift.integrations.base import ProviderError
from ghostshift.schemas.common import ProviderInfo, ProviderKind, StageStatus
from ghostshift.schemas.copilot import ChatTurn
from ghostshift.schemas.workflow import ActionStatus

from .conftest import CRAH


class FakeConverse:
    """Scripted Bedrock Converse client. Each reply is a list of content blocks or an exception."""

    info = ProviderInfo(name="fake-bedrock", kind=ProviderKind.external, real=True, model_id="fake-model")

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def converse(self, *, system, messages, tools, max_tokens=1200):
        self.requests.append({"system": system, "messages": json.loads(json.dumps(messages)), "tools": tools})
        r = self.replies[min(len(self.requests) - 1, len(self.replies) - 1)]
        if isinstance(r, BaseException):
            raise r
        return {"message": {"role": "assistant", "content": r}, "stop_reason": "end_turn", "usage": {},
                "latency_ms": 1.0}


def use(name, tool_id="t1", **inp):
    return {"toolUse": {"toolUseId": tool_id, "name": name, "input": inp}}


def text(t):
    return {"text": t}


def at_fault(container, cursor=216):
    container.orchestrator.set_cursor(CRAH, cursor)
    container.orchestrator.monitor(CRAH)
    return container.store.open_incident_for(CRAH)


def copilot(container, llm, aws=False):
    return Copilot(CopilotTools(container), llm, report_failures=aws)


def test_tool_specs_are_valid_converse_schemas(container):
    specs = CopilotTools(container).specs()
    names = [s["toolSpec"]["name"] for s in specs]
    assert len(names) == len(set(names)) >= 8
    for s in specs:
        schema = s["toolSpec"]["inputSchema"]["json"]
        assert schema["type"] == "object" and "properties" in schema
        assert all("anyOf" not in p for p in schema["properties"].values())
    forbidden = ("approve", "reject", "execute", "order", "send", "dispatch", "priority", "submit")
    assert not [n for n in names if any(f in n for f in forbidden)]


def test_every_tool_runs_at_fault(container):
    inc = at_fault(container)
    tools = CopilotTools(container)
    args = {"list_machines": {}, "get_inventory": {}, "get_sensor_readings": {"machine_id": CRAH},
            "search_parts": {"machine_id": CRAH}}
    for name in tools.tools:
        _, out = tools.call(name, args.get(name, {"machine_id": CRAH}))
        json.dumps(out, default=str)
    _, i = tools.call("get_incident", {"machine_id": CRAH})
    assert i["incident_id"] == inc.id and i["priority"] == "High"


def test_multi_step_tool_loop_returns_model_answer(container):
    at_fault(container)
    llm = FakeConverse([use("get_incident", "a", machine_id=CRAH)],
                       [use("get_time_to_limit", "b", machine_id=CRAH), use("run_diagnostics", "c", machine_id=CRAH)],
                       [text("MF-07 is High priority because the fan bearing is wearing (diagnostics).")])
    out = copilot(container, llm).ask(machine_id=CRAH, question="Why was this flagged?")
    assert out.status == StageStatus.success and not out.built_in and out.provider.real
    assert [c.name for c in out.tool_calls] == ["get_incident", "get_time_to_limit", "run_diagnostics"]
    assert all(c.ok for c in out.tool_calls)
    assert {c.agent for c in out.tool_calls} == {"safety supervisor", "prognostics", "diagnostics"}
    last = llm.requests[-1]["messages"][-1]
    assert last["role"] == "user" and {b["toolResult"]["toolUseId"] for b in last["content"]} == {"b", "c"}
    assert "machine MF-07" in llm.requests[0]["messages"][0]["content"][0]["text"]


def test_tool_call_bound_is_enforced(container):
    at_fault(container)
    llm = FakeConverse([use("get_incident", "x", machine_id=CRAH)])  # never stops calling tools
    out = copilot(container, llm).ask(machine_id=CRAH, question="Why?")
    model_calls = [c for c in out.tool_calls if c.name == "get_incident" and c.agent == "safety supervisor"]
    assert sum(1 for c in model_calls if c.ok) <= MAX_TOOL_CALLS + 1  # +1 from the built-in fallback
    assert any(not c.ok and "limit" in c.summary for c in out.tool_calls)
    assert out.status == StageStatus.deterministic_fallback and out.built_in


def test_invalid_arguments_are_returned_to_the_model(container):
    at_fault(container)
    llm = FakeConverse([use("get_sensor_readings", "a", machine="MF-07")], [text("Fixed it.")])
    out = copilot(container, llm).ask(machine_id=CRAH, question="Readings?")
    assert out.status == StageStatus.success and not out.tool_calls[0].ok
    result = llm.requests[1]["messages"][-1]["content"][0]["toolResult"]
    assert result["status"] == "error" and "Invalid input" in result["content"][0]["text"]


def test_forbidden_tool_is_refused_and_nothing_changes(container):
    inc = at_fault(container)
    before = {a: container.store.actions[a].status for a in inc.action_ids}
    llm = FakeConverse([use("approve_action", "a", action_id=inc.action_ids[0])],
                       [text("I can't approve; a supervisor does that in GhostShift.")])
    out = copilot(container, llm).ask(machine_id=CRAH, question="Approve the part order for me.")
    assert not out.tool_calls[0].ok and "Unknown tool" in out.tool_calls[0].summary
    assert {a: container.store.actions[a].status for a in inc.action_ids} == before
    assert all(s == ActionStatus.awaiting_approval for s in before.values())
    assert container.store.open_incident_for(CRAH).safety == inc.safety


def test_provider_failure_auto_falls_back_aws_reports(container):
    at_fault(container)
    boom = ProviderError("Bedrock ThrottlingException: slow down", retryable=True)
    auto = copilot(container, FakeConverse(boom)).ask(machine_id=CRAH, question="Why was this flagged?")
    assert auto.status == StageStatus.deterministic_fallback and auto.built_in and "Throttling" in auto.error
    assert "High priority" in auto.answer
    aws = copilot(container, FakeConverse(boom), aws=True).ask(machine_id=CRAH, question="Why was this flagged?")
    assert aws.status == StageStatus.provider_failure and not aws.built_in and "Throttling" in aws.answer


def test_unsafe_answer_is_rejected(container):
    at_fault(container)
    llm = FakeConverse([text("The fan tray has been isolated, so it is safe to work on.")])
    out = copilot(container, llm, aws=True).ask(machine_id=CRAH, question="Can I start?")
    assert out.status == StageStatus.invalid_result and "safe" not in out.answer.split(":")[0]


def test_built_in_answers_without_a_model(container):
    at_fault(container)
    c = copilot(container, None)
    why = c.ask(machine_id=CRAH, question="Why was this flagged?")
    assert why.status == StageStatus.success and why.built_in and "Diagnostics matched" in why.answer
    wait = c.ask(machine_id=CRAH, question="What happens if we wait until the weekend?")
    assert "earliest" in wait.answer and any(t.name == "get_maintenance_windows" for t in wait.tool_calls)
    parts = c.ask(machine_id=CRAH, question="Which other parts should we check?")
    assert parts.built_in and parts.answer


def test_normal_machine_and_unknown_machine(container):
    out = copilot(container, None).ask(machine_id=CRAH, question="Why was this flagged?")
    assert "Nothing is flagged" in out.answer and out.incident_id is None
    with pytest.raises(ToolError):
        copilot(container, None).ask(machine_id="FAN-9", question="Vibration?")


def test_history_becomes_alternating_converse_messages():
    h = [ChatTurn(role="assistant", text="hi"), ChatTurn(role="user", text="a"), ChatTurn(role="user", text="b"),
         ChatTurn(role="assistant", text="c"), ChatTurn(role="user", text="dangling")]
    msgs = _history_messages(h)
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[0]["content"][0]["text"] == "a\nb"


def test_ask_endpoint_demo_mode(client):
    client.post(f"/api/machines/{CRAH}/replay", json={"action": "seek", "cursor": 216})
    r = client.post("/api/copilot/ask", json={"machine_id": CRAH, "question": "Why was this flagged?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["built_in"] and body["status"] == "success" and body["tool_calls"]
    assert len(body["suggested_questions"]) == 3
    assert client.post("/api/copilot/ask", json={"machine_id": "NOPE", "question": "x"}).status_code == 404
