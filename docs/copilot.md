# GhostMode copilot (Bedrock chat that coordinates the agents)

GhostMode is the chat panel at the bottom of a machine's page ("Ask GhostMode"). A Bedrock model
answers questions by calling GhostShift's specialist agents as **read-only tools**, then combines
their answers. Code: `backend/ghostshift/agents/copilot.py`, route `POST /api/copilot/ask`
(`api/copilot_routes.py`), UI `frontend/src/features/copilot/`.

## Tools (all read-only)

| Tool | Specialist | Returns |
|---|---|---|
| `list_machines` | site | Machines, condition, open problem |
| `get_machine_status` | diagnostics | Condition, open problem, component health |
| `get_sensor_readings` | diagnostics | Latest readings vs normal range and limits |
| `run_diagnostics` | diagnostics | Abnormal readings, matched fault pattern |
| `get_time_to_limit` | prognostics | Time to danger limit (range), risk, service due |
| `get_incident` | safety supervisor | Priority and why, approvals, part, slot, steps |
| `search_parts` | maintenance & supply | Parts that fit, price, stock, lead time |
| `get_maintenance_windows` | maintenance & supply | Planned windows, redundant unit, bookings |
| `get_inventory` | inventory | Stock, orders, reorder suggestions (simulated) |

There is no tool to approve, reject, execute, order, change priority or send messages. An unknown
tool name is refused and returned to the model as a tool error.

## Limits and safety

- At most 6 tool calls and 8 model turns per question; tool input is validated with Pydantic.
- Answers claiming equipment is safe or isolated are rejected (same filter as the narrative).
- The model never sets priority or approvals; those stay in `agents/safety.py` and `approvals.py`.

## Modes

| Mode | Behaviour |
|---|---|
| `demo` | Built-in answers for the three suggested questions, from the same tools. Labelled "Built-in answer". |
| `auto` | Bedrock if `GHOSTSHIFT_BEDROCK_MODEL_ID` is set. Any failure falls back to the built-in answer, labelled Fallback, with the error. |
| `aws` | Bedrock; failures are reported, never replaced. |

## Model

This event's account allows the OpenAI profiles only. Tested: `us.openai.gpt-5.6-luna`
(`make check-bedrock`). GPT-5.x rejects `temperature`, so the Converse calls send none.
If tool calls fail with a ValidationException, try `us.openai.gpt-5.6-sol` or `us.openai.gpt-5.5`.

## Try it

`GHOSTSHIFT_MODE=auto`, `GHOSTSHIFT_BEDROCK_MODEL_ID=us.openai.gpt-5.6-luna`, `make dev`, open MF-07,
press *Skip to fault*, then ask "Why was this flagged?". The answer's *Steps* list shows which agents
it consulted.

```bash
curl -s localhost:8000/api/copilot/ask -H 'content-type: application/json' \
  -d '{"machine_id":"MF-07","question":"Why was this flagged?"}'
```
