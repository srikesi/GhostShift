---
name: agent-workflow
description: Change GhostShift's agents or orchestration — add a stage, modify diagnostics/prognostics/safety/maintenance logic, add LLM reasoning, or deploy agents to AgentCore — while preserving typed contracts, safety gates and honest status reporting.
---

# Change the agent workflow

## Purpose
Keep agents small, typed and independently testable; keep execution order, timeouts and failure handling in the orchestrator; keep safety deterministic.

## When to use
- Adding/modifying an agent or a workflow stage.
- Using Bedrock (or another LLM) for more than narrative wording.
- Packaging the workflow for Bedrock AgentCore or another runtime.

## Inspect first
- `backend/ghostshift/schemas/agents.py` — stage inputs/outputs (all `extra="forbid"`).
- `backend/ghostshift/agents/*.py` — one class per agent with `run(input) -> result`.
- `backend/ghostshift/orchestrator.py` — stage order, `_stage` (timeout + exception → status), `_narrative` (LLM retries/fallback), `_persist`, `_notify`, `monitor`.
- `backend/ghostshift/approvals.py` — the approval gate.
- `StageStatus` in `schemas/common.py`: success, deterministic_fallback, provider_failure, invalid_result, skipped.

## Rules
- Agents never import FastAPI, construct providers, or read settings; dependencies are injected.
- Safety tiers and approval requirements are computed in `SafetySupervisor` code. An LLM may explain; it may not set or lower a tier, remove an approval, or claim equipment is safe/isolated (`narrative.FORBIDDEN`).
- Risk score and RUL stay separate. RUL needs a supportable trend; otherwise `supportable=False` with a reason.
- Every LLM output is parsed into a Pydantic model; bounded retries; fall back (auto) or report (aws). Never present a fallback as a model result.
- Operational side effects only through `ApprovalService.execute` after all required roles approve.

## Checklist
1. Define/extend the input and output contracts first.
2. Implement the agent as a pure class; add a deterministic implementation even if an LLM version exists.
3. Wire the stage in `Orchestrator._execute` via `_required` (mandatory) or `_stage` (optional, failure tolerated). Record warnings on the `StageRecord`.
4. Surface new fields in the frontend types (`frontend/src/api/types.ts`) and the relevant panel.
5. AgentCore: wrap `build_container()` + `orchestrator.run()` in the AgentCore entrypoint; keep the FastAPI app as the local runtime. Do not split agents into separate services unless the event requires it.

## Tests required before done
- Direct agent tests with fixture windows (normal and anomalous) — no LLM.
- Orchestrator tests for the new stage: success, exception → failed/continued, timeout.
- If LLM-backed: FakeLLM tests for success, retryable error, invalid output, unsafe output, auto vs aws status.
- `tests/test_approval_gate.py` still passes unchanged; `make demo-smoke` passes.
