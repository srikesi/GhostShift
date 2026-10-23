# Workstream 1: Agentic copilot (Bedrock tool use)

**Prompt to give the agent:**

> You are finishing the Faultzy hackathon project (AWS Agentic AI Hackathon, Track 2). Pull `main`, then read `README.md`, `docs/workstreams/README.md` (ownership and git rules: follow them exactly) and this file, `docs/workstreams/1-agentic-copilot.md`. Complete workstream 1 and push to `main` in small, verified commits. Only edit files your workstream owns.

## Why
Today every agent is deterministic, and Bedrock only rewords the incident summary (by default, the built-in template does). For an *agentic* AI track, the judges need to see a model that reasons and uses tools. The safety gates must stay in code.

## Goal
Add a Bedrock-powered copilot. It answers questions about a machine or incident by calling Faultzy's existing deterministic functions as tools, and it can run an investigation when an incident opens.

## Build
1. **Tool-use loop.** In `integrations/bedrock.py`, add tool use through the Converse API (`toolConfig`). The loop is bounded (for example, at most 6 tool calls), has per-call timeouts, and maps errors to `ProviderError`. Keep the existing `complete()` working.
2. **Tools** (in a new module under `backend/faultzy/agents/`) are read-only wrappers over existing code:
   - machine status and component health
   - sensor readings for a time range
   - run diagnostics at the current cursor
   - time-to-limit estimate
   - parts catalog search
   - downtime windows
   - incident detail
   - draft a work order (returns a draft only)

   No tool may approve, reject or execute actions, change a priority tier, or send messages. Validate every tool input with Pydantic, and return errors to the model as tool results.
3. **API.** Add `POST /api/copilot/ask` with `{machine_id, incident_id?, question}`. It returns `{answer, tool_calls[], status, provider}`, using the existing `StageStatus` values. Add endpoints only in `api/copilot_routes.py`, which is already registered.
4. **Modes.**
   - `demo`: no network. Return a clearly labelled built-in answer for a few suggested questions, built from the same tools without a model. Otherwise say the copilot needs Bedrock.
   - `auto`: use Bedrock if configured, otherwise fall back with a label.
   - `aws`: report failures; don't mask them.
5. **Investigation (optional, if time allows).** When the orchestrator opens or escalates an incident, the copilot may write the narrative by calling tools. Validate the output exactly as `agents/narrative.py` does (including the unsafe-claim filter). Fall back to the template.
6. **UI.** Implement `frontend/src/features/copilot/CopilotPanel.tsx`; it's already rendered on the dashboard.
   - A question box and 3 suggested questions, such as "Why was this flagged?", "What happens if we wait until the weekend?" and "Which other parts should we check?".
   - The answer, plus a collapsed "Steps" list of the tool calls.
   - Put types and fetch calls in `features/copilot/`. Add no new npm dependencies. Follow the ui-quality skill: plain words, and show the provider label only when a live model was used, fell back or failed.
7. **AgentCore / Strands.** Only if the organizers require it: add `backend/agentcore/` with an entrypoint that builds the container and calls the same copilot. FastAPI remains the local runtime.

## Verify before declaring done
- `make check-bedrock` succeeds in the workshop account. Record the model id you chose in `docs/copilot.md`, but never credentials.
- New tests in `backend/tests/test_copilot_*.py`, using a scripted fake client:
  - a multi-step tool loop
  - the step bound being hit
  - invalid tool arguments
  - provider failure in auto and in aws mode
  - an attempt to call a non-existent or forbidden tool
  - the answer never changing tier or approvals
- `make check` is green. With `FAULTZY_MODE=demo`, `make demo-smoke` passes.
- Manual check: with `FAULTZY_MODE=auto` and a model id, ask the 3 suggested questions in the UI on VMC-07 at "Skip to fault". Answers cite real numbers from tools.
- `docs/copilot.md` documents the tools, modes, model id and limits.
