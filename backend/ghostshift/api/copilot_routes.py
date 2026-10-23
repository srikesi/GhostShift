"""Copilot API (agentic Bedrock layer). Owned by docs/workstreams/1-agentic-copilot.md.

Registered in `ghostshift.main`. Add endpoints here; keep them under /api/copilot.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..agents.copilot import Copilot, CopilotTools, ToolError
from ..config import ExecutionMode
from ..container import Container
from ..schemas.copilot import CopilotAnswer, CopilotAskRequest
from .routes import get_container

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


def build_copilot(c: Container) -> Copilot:
    """Model choice follows the mode contract: demo = built-in answers; auto = Bedrock if configured,
    else built-in (labelled); aws = Bedrock, failures reported."""
    llm = c.llm if c.llm is not None and hasattr(c.llm, "converse") else None
    mode = c.settings.mode
    reason = None
    if llm is None and mode != ExecutionMode.demo:
        reason = "Bedrock is not configured (set GHOSTSHIFT_BEDROCK_MODEL_ID); using built-in answers"
    return Copilot(CopilotTools(c), llm, report_failures=mode == ExecutionMode.aws, fallback_reason=reason,
                   deadline_s=max(30.0, c.settings.llm_timeout_s * 4))


@router.post("/ask", response_model=CopilotAnswer)
def ask(body: CopilotAskRequest, c: Container = Depends(get_container)) -> CopilotAnswer:
    try:
        return build_copilot(c).ask(machine_id=body.machine_id, question=body.question,
                                    incident_id=body.incident_id, history=body.history)
    except ToolError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
