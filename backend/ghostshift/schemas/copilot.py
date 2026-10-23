"""Contracts for the GhostMode copilot: a Bedrock chat agent that coordinates the specialist agents."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .common import Contract, ProviderInfo, StageStatus


class ChatTurn(Contract):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class CopilotAskRequest(Contract):
    machine_id: str
    incident_id: str | None = None
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12,
                                    description="Earlier turns of this chat, oldest first")


class ToolCallRecord(Contract):
    name: str
    agent: str = Field(description="Which GhostShift specialist answered (shown in the Steps list)")
    input: dict[str, Any]
    ok: bool
    summary: str = Field(description="One line on what the tool returned, or the error")
    duration_ms: float


class CopilotAnswer(Contract):
    machine_id: str
    incident_id: str | None
    answer: str
    tool_calls: list[ToolCallRecord]
    status: StageStatus
    provider: ProviderInfo
    built_in: bool = Field(description="True when the answer came from GhostShift's built-in rules, not a model")
    error: str | None = None
    suggested_questions: list[str] = Field(default_factory=list)
