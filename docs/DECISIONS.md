# Faultzy: decisions and assumptions

Recorded during the initial build (2026-10-23). Revisit when the organizers publish final requirements.

## Decisions

1. **Modular monolith, explicit orchestrator.** Agents are in-process classes with typed `run()` methods, and the orchestrator owns order, timeouts and failure mapping. There are no per-agent services. This is the fastest path to a reliable demo, and the same container can be wrapped for AgentCore later.
2. **Deterministic core, LLM at the edge.** Diagnostics, prognostics, safety and maintenance planning are deterministic code. Bedrock is used only to reword the incident narrative, under schema validation, bounded retries and an unsafe-claim filter. This keeps the demo reproducible offline and keeps safety gates out of model control.
3. **Risk ≠ RUL.** The risk score is the fraction of the baseline-to-danger margin projected to be consumed within 24 h (uncalibrated). RUL is the time for a linear trend to reach the danger limit, reported only when the slope's t-statistic is at least 3, with a ±2 SE interval. Components with no deviation get no trend RUL; their schedule-based "service due" is shown separately.
4. **Monitor only escalates.** The replay monitor re-runs the workflow when severity or tier increases for an open incident. Tier is never lowered automatically, and approval requirements only tighten.
5. **Approval gate in the backend.** `ApprovalService` checks roles, the isolation attestation and full approval before any execute. The UI only reflects it.
6. **Mode contract.** `demo`: all stubs. `auto`: real if configured, otherwise a labelled fallback. `aws`: real, with failures surfaced. Provider choice lives only in `container.py`.
7. **SVG schematic over 3D.** Named parts (`visualization_id`) give a useful, robust highlight with no WebGL dependency. A GLB viewer can adopt the same ids.
8. **No database.** In-memory state is enough for the demo. `Store` is the seam for SQLite or DynamoDB.
9. **Inspection links.** A random 18-byte token, stored as a SHA-256 hash, scoped to one incident, read-only, expiring after 12 h. Unknown and expired tokens return the same 404.
10. **Fonts bundled** (@fontsource), so the UI renders identically offline.

## Assumptions

- Sensor limits are site alarm limits supplied as fixtures, not physical failure points.
- 15-minute sampling, with a 24 h baseline window per scenario.
- The fixture technician phone numbers are fictional. Real SMS only goes to an explicitly configured number.
- Python 3.12 via uv. The code requires Python 3.11 or later.
- No model id is assumed for Bedrock. `make check-bedrock` must be run in the workshop account.
