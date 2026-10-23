GhostShift is a multi agent system that listens to your machines, understands what they're saying using sensor data, machine manuals, and expert knowledge and acts.

# GhostShift

GhostShift is a predictive-maintenance and maintenance-coordination app built for the Austin AWS Agentic AI Hackathon (Track 2: Autonomic Shop Floor & Predictive Maintenance). It detects machine anomalies, explains the evidence, estimates risk and remaining useful life with uncertainty, proposes parts and a work order, enforces human approval, and sends the technician an SMS with a link to a mobile inspection page.

It runs **fully offline by default**. AWS credentials, Twilio and ElevenLabs are optional.

```
backend/   FastAPI modular monolith: agents, orchestrator, integrations, fixtures, tests
frontend/  React + TypeScript + Vite: operations dashboard and mobile inspection view
.claude/skills/  Repo-specific Claude Code skills (integrations, datasets, agents, UI, demo)
docs/DECISIONS.md  Architecture decisions and assumptions
```

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you), and Node 18+ with npm.

```bash
make setup
```

```bash
make dev
```

Then open http://localhost:5173. The API is at http://localhost:8000 (`/docs` for OpenAPI, `/api/health` for status).

Without `make`, run the two halves separately:

```bash
cd backend && uv sync --extra dev && uv run uvicorn ghostshift.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

pip also works: `cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.

## Demo script (about 3 minutes)

1. **Normal.** CRAH-07 opens with every sensor inside its shaded normal range. The small marker above the timeline shows where the simulated fault starts; GhostShift never sees that marker.
2. **Play.** Readings advance 30 min per tick. Around sample 170, the supply fan's vibration on CRAH-07 leaves its normal range. GhostShift opens a problem at **Medium** priority and pauses. *Why it was flagged* shows the readings against normal and the matching fault pattern. No alarm limit has been crossed yet.
3. **Play again.** At sample 174 the earliest time-to-limit estimate drops under 72 h. Priority goes to **High** and the technician gets a text, still before any alarm limit is crossed. The problem card shows the time to the danger limit as a range, the next downtime, and the part.
4. **Recommended fix.** The bearing kit `GS-BRG-FAN-KIT` ($240) is in the critical spares cage, the planned maintenance window (with CRAH-08 covering the load) comes before the earliest limit estimate, and the steps start with confirming the redundant unit is carrying the load.
5. **Approvals.** Approve the part order, then *Send order*. You get `SIM-PR-00001`, a simulated record. Next, try approving the work order without ticking the lockout/tagout box: the backend refuses. Tick it and the approval goes through.
6. **Technician view.** Click *Technician view* (or open the texted link on a phone). The affected part is highlighted on the drawing, with the readings, time to limit, job steps and the other parts.
7. **Escalation (optional).** Play to the end. At sample 226 priority becomes **Urgent**, a second text says "ESCALATED", and the work order now also needs the operations manager.
8. **Second machine.** CH-02 → *Skip to fault*: oil-cooler fouling. The in-stock cleaning kit beats a replacement core with a 3-day lead time, and GhostShift warns that the next planned downtime may be too late.

## Autonomy demo (about 1 minute)

GhostShift runs every step on its own except the ones that need a person by policy.

1. Click **Reset**, then turn on **Autopilot** in the top bar ("orders parts up to $2,500").
2. Press **Play** and don't touch anything else. GhostShift pauses when it flags the problem (Medium priority). *What GhostShift did* shows it already drafted the part order and the work order, and it is **holding** the order until priority is High.
3. Press **Play** again. At High priority the **Autopilot** places the $240 bearing kit order itself (simulated), texts the technician with "Part ordered", and the timeline shows "10 on its own · 0 by people".
4. The only step left is **You: approve work order (lockout/tagout sign-off)**. Physical work never runs without a person, even on Autopilot.
5. Turn Autopilot off and reset to show the contrast: the same run stops at "Approve the order" and waits.

Autopilot rules (deterministic code in `orchestrator.py`): High or Urgent priority, only the maintenance supervisor's approval required, cost within the limit (`GHOSTSHIFT_AUTO_ORDER_LIMIT_USD`), and the part in stock or arriving before the earliest estimated limit. Orders over the limit, or ones needing the operations manager, are held for a person with the reason logged.

*How GhostShift decided* (collapsed, at the bottom of the problem column) holds the rule details, priority reasons, estimate method, limitations and the step-by-step log. **Reset** in the top bar clears all state, and so does restarting the API.

UI wording: sensor condition is *Normal / Watch / Warning / Critical*. Problem priority is *Low / Medium / High / Urgent* (the safety tiers routine / elevated / high / critical). Outputs that only exist in the simulation (texts, orders, stock) carry a small *Simulated* tag, and the top bar says "Demo · simulated data".

## Get the technician text on your phone

When a problem reaches High priority, GhostShift texts the technician a link to a phone page. The page shows the machine drawing with the part to replace highlighted. Tap any part to see its condition, readings, time to limit and service date.

```bash
make text-me
```

Run this with the API up. It triggers the CRAH-07 fault and prints the text and its link. In demo mode the text is recorded, not sent. To get a real text, set these in `.env` and restart the API:

- `GHOSTSHIFT_MODE=auto` and `GHOSTSHIFT_SMS_PROVIDER=twilio`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- `GHOSTSHIFT_DEMO_TECHNICIAN_PHONE`: your phone. Twilio trial accounts can only text verified numbers.
- `GHOSTSHIFT_PUBLIC_BASE_URL`: an address your phone can open, using a domain name: WhatsApp and many SMS apps don't make bare IP addresses tappable. On the same Wi-Fi, use your LAN IP through sslip.io, e.g. `http://172-24-127-47.sslip.io:5173` with `npm run dev -- --host`, or use the deployed URL.
- Phone on a different network (or venue Wi-Fi that blocks device-to-device traffic)? Use a free Cloudflare quick tunnel: `brew install cloudflared`, run `cloudflared tunnel --url http://localhost:5173`, and set `GHOSTSHIFT_PUBLIC_BASE_URL` to the `https://….trycloudflare.com` address it prints, then restart the API. The address changes each time the tunnel restarts, and anyone with it can open the dashboard, so stop the tunnel when you're done.
- No registered US number yet? Unregistered 10-digit senders are blocked by US carriers (Twilio error 30034). The Twilio WhatsApp sandbox works today: join it from your phone, then set `TWILIO_FROM_NUMBER=whatsapp:+14155238886`.

## Team workstreams

The remaining hackathon work is split into four parallel workstreams with file ownership and a git protocol, so several agents can push to `main` without conflicts. See [docs/workstreams/README.md](docs/workstreams/README.md).

## Architecture

A modular monolith with an explicit orchestrator. Agents are plain typed classes, and providers are injected.

```
 telemetry ─▶ diagnostics ─▶ prognostics ─▶ safety_supervisor ─▶ maintenance_supply
                                                                   │
              notification ◀─ records ◀─ narrative (LLM optional) ◀─ safety_gate (re-check with cost)
```

| Module | Responsibility |
|---|---|
| `ghostshift/schemas/` | Pydantic v2 contracts (`extra="forbid"`) for every stage, record and API response |
| `ghostshift/agents/diagnostics.py` | Baseline z-score, persistence, alarm limits, rule-based fault signatures, evidence refs |
| `ghostshift/agents/prognostics.py` | Failure-risk score (uncalibrated) and RUL via linear trend to the danger limit, with a ±2 SE interval. RUL is reported only when the trend is statistically supportable. Interval-based service due is reported separately |
| `ghostshift/agents/safety.py` | Deterministic tiering (routine/elevated/high/critical), escalation, required approvals, safety notices |
| `ghostshift/agents/maintenance.py` | Part matching and ranking, downtime-window proposal, work-order draft |
| `ghostshift/agents/narrative.py` | Deterministic incident text. Optionally reworded by Bedrock, with validated output; unsafe claims are rejected |
| `ghostshift/orchestrator.py` | Stage order, per-stage timeouts, exception → status mapping, incident/record persistence, notifications, replay monitor |
| `ghostshift/approvals.py` | Approval gate: role checks, isolation attestation, execute-only-when-approved |
| `ghostshift/integrations/` | Provider Protocols (`base.py`), stubs and real adapters |
| `ghostshift/container.py` | The only place that picks real or stub implementations from configuration |
| `ghostshift/state.py` | In-memory store, plus hashed, expiring inspection-link tokens |

### Statuses are distinct
Stage results are `success`, `deterministic_fallback`, `provider_failure`, `invalid_result` or `skipped`. Actions are `awaiting_approval`, `approved`, `rejected`, `completed_simulated`, `completed` or `failed`. Workflow runs are `completed`, `completed_no_incident`, `awaiting_approval` or `failed`. A failed provider call never looks like a success: the UI shows FALLBACK or FAILED tags, and the trace records the error.

### Execution modes (`GHOSTSHIFT_MODE`)
| Mode | Behaviour |
|---|---|
| `demo` (default) | Every provider is a deterministic stub. No network calls. |
| `auto` | Uses Bedrock if `GHOSTSHIFT_BEDROCK_MODEL_ID` is set. LLM errors and invalid output fall back to the template, labelled `deterministic_fallback`. Twilio and ElevenLabs are used only if selected **and** configured; otherwise stubs. Runtime failures of a configured SMS or voice provider are reported, not masked. |
| `aws` | Selected real providers are used even if misconfigured, so failures surface as `provider_failure` or `failed`. No silent fallback. |

Diagnosis, risk, safety and approvals are deterministic in every mode. The LLM only writes the narrative.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health?probe=false` | Mode, provider configuration and availability (probe=true makes live calls) |
| GET | `/api/machines` · `/api/machines/{id}` | Summaries; detail with screening and component health |
| GET | `/api/machines/{id}/telemetry` | Window up to the replay cursor, scenario labels, detection segments |
| POST | `/api/machines/{id}/replay` | `{"action": "reset"\|"advance"\|"seek"\|"to_end", "steps", "cursor"}`. Runs the monitor |
| POST | `/api/machines/{id}/workflow` | Run the full workflow now (201) |
| GET | `/api/workflows`, `/api/workflows/{id}` | Run traces |
| GET | `/api/incidents`, `/api/incidents/{id}` | Incident with actions, records, notifications, latest run |
| GET | `/api/incidents/{id}/briefing` | Voice briefing (text always, audio if available) |
| GET | `/api/approvals?status=` | Gated actions |
| POST | `/api/actions/{id}/decision` | `{role, approver_name, decision, isolation_attestation}`. Returns 403 wrong role, 409 not pending, 422 missing attestation |
| POST | `/api/actions/{id}/execute` | Returns 409 unless every required role approved |
| GET | `/api/work-orders`, `/api/requisitions`, `/api/notifications` | Records |
| GET | `/api/inspect/{token}` | Token-scoped mobile payload. Unknown and expired tokens both return 404 |
| GET / PUT | `/api/autonomy` | Read or change Autopilot (`{"level": "advise" \| "autopilot", "auto_order_limit_usd"}`). Turning it on applies to open problems immediately |
| POST | `/api/demo/reset` | Clear state (keeps the Autopilot setting) |

Errors always use the form `{"error": {"code", "message", "details"}}`.

## Integration points (for new hackathon requirements)

| Capability | Interface (`integrations/base.py`) | Today | Real adapter | Selected in |
|---|---|---|---|---|
| LLM | `LlmProvider` | template | `bedrock.py` (Converse, boto3) | `choose_llm` |
| Telemetry | `TelemetryProvider` | `telemetry_fixture.py` | `ai4i.py` (dataset), add e.g. Timestream, IoT SiteWise or S3 | `build_container` |
| Parts catalog | `PartsCatalogProvider` | `supply.FixturePartsCatalog` | add ERP or catalog API | `build_container` |
| Procurement | `ProcurementProvider` | `supply.SimulatedProcurement` | add ERP | `build_container` |
| Work orders | `WorkOrderProvider` | `supply.SimulatedWorkOrders` | add CMMS | `build_container` |
| SMS | `SmsProvider` | `sms.SimulatedSms` | `sms.TwilioSms` | `choose_sms` |
| Voice | `VoiceProvider` | `voice.TextOnlyVoice` | `voice.ElevenLabsVoice` | `choose_voice` |

The fastest path for a newly announced service:
1. Read the official docs and the organizers' starter code.
2. Follow `.claude/skills/add-integration/SKILL.md`: add an adapter, wire it in `container.py`, add a mocked test, and update `.env.example`.
3. Keep `GHOSTSHIFT_MODE=demo` green (`make check`, `make demo-smoke`).

For AgentCore, wrap `build_container()` and `orchestrator.run(machine_id)` in the AgentCore entrypoint and keep FastAPI as the local runtime (see `.claude/skills/agent-workflow`).

### Bedrock
Model access differs between accounts. Do not assume a model id:

```bash
make check-bedrock
```

This prints your AWS identity, the text models and inference profiles visible in the region, and the result of a test Converse call. Many newer models must be called through an inference profile id (such as `us.…`). The role needs `bedrock:InvokeModel` on the profile and on the underlying model. Then set `GHOSTSHIFT_MODE=auto` and `GHOSTSHIFT_BEDROCK_MODEL_ID`.

### Twilio (opt-in)
Set `GHOSTSHIFT_SMS_PROVIDER=twilio`, the three `TWILIO_*` values, and `GHOSTSHIFT_DEMO_TECHNICIAN_PHONE`. Real SMS only ever goes to that number; the fixture phone numbers (fictional 555-01xx) are never dialled. Retries are bounded: 5xx and 429 are retried, other 4xx are not. For a phone to open the link, set `GHOSTSHIFT_PUBLIC_BASE_URL` to a reachable address (for example run `npm run dev -- --host` and use your LAN IP).

### ElevenLabs (optional)
Set `GHOSTSHIFT_VOICE_PROVIDER=elevenlabs`, `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`. If audio fails, the briefing text is still returned. Voice is never required for diagnosis, notification or approval.

### AI4I 2020 dataset
Download `ai4i2020.csv` (UCI, CC BY 4.0) and set `GHOSTSHIFT_AI4I_PATH`. This registers machine `AI4I-MILL`. The adapter converts K to °C, synthesizes timestamps (labelled), and keeps failure labels out of agent inputs. The dataset has no vibration, bearing temperature or motor current, and its rows are not a run-to-failure trajectory, so trend RUL will generally be reported as not supportable.

## Environment variables
All variables are listed with safe placeholders in [.env.example](.env.example). Copy it to `.env` in the repo root. Credentials stay server-side (environment or AWS credential chain) and are never sent to the browser.

## Testing

```bash
make check
```

This runs the backend pytest suite (68 tests), the frontend type check, and the production build.

```bash
make demo-smoke
```

Run this with the API up. It replays CRAH-07 end to end and asserts each step of the story.

Tests cover each agent without an LLM; the orchestrator with fake LLMs (success, retryable, non-retryable, invalid, unsafe, timeout, auto vs aws); the approval gate (no execute before approval, wrong role, attestation, rejection, partial approval, double decision); API contracts; inspection-token scoping and expiry; and every adapter with the network mocked (Twilio, ElevenLabs, Bedrock, AI4I).

## What is real and what is simulated

| Item | Status |
|---|---|
| Telemetry for CRAH-07 / CH-02 | **Simulated** (deterministic, `scripts/generate_fixtures.py`) |
| Machines, limits, maintenance history, parts, prices, calendar | **Fixture** reference data |
| Stock and lead times | **Simulated**, not live inventory |
| Diagnostics, risk, RUL, safety tier | **Deterministic analysis** on the data above (derived from simulated data) |
| Energy and lube readings (fan and compressor power, humidifier water pressure and level, oil-separator pressure drop, oil level) | **Simulated** |
| Autopilot ordering | Real policy decision; the order itself is **simulated** |
| Narrative | Deterministic template, or **real Bedrock inference** when configured |
| Requisitions and work-order dispatch | **Simulated**; nothing is ordered or created in an external system |
| SMS | Recorded (simulated), or **real Twilio** when opted in |
| Voice | Text only, or **real ElevenLabs** audio when configured |

## Safety and authorization
- Tiers and approval requirements are code (`agents/safety.py`). LLM output cannot change them. Narratives claiming equipment is safe or isolated are rejected.
- Approvals authorise a record in GhostShift. They do not stop, isolate or make equipment safe, and the UI says so wherever approvals appear.
- Work-order approval requires attesting that isolation will be performed and verified by qualified personnel under the site LOTO procedure. Checklists are reference only.
- Execution is refused (409) until every required role has approved. The approver role is declared in the request; real authentication is not implemented yet (see limitations).
- Inspection links carry a random token that is scoped to one incident, read-only and expiring, and stored only as a hash. No credentials or personal information appear in the SMS.

## Troubleshooting
- **UI says "GhostShift API is unreachable".** Start the backend on :8000 (`make api`). Vite proxies `/api` there; override with `GHOSTSHIFT_API_URL`.
- **`uv: command not found`.** Install it with `brew install uv`, or use the pip instructions above.
- **Port in use.** Run `lsof -i :8000` or `lsof -i :5173` and stop the old process.
- **Bedrock `AccessDeniedException`.** Enable model access in the Bedrock console for the region and check IAM. **`ValidationException … inference profile`**: use the `us.`/`eu.` profile id listed by `cd backend && uv run python scripts/check_bedrock.py --list`.
- **Twilio 21211 / 21608.** The number is invalid or unverified (trial accounts can only text verified numbers).
- **SMS link does not open on a phone.** `GHOSTSHIFT_PUBLIC_BASE_URL` must be reachable from the phone.
- **State looks stale.** Click *Reset demo* or restart the API (all state is in memory).

## Known limitations
- State is in memory and single-process. A restart clears incidents.
- There is no user authentication. Approver identity and role are self-declared in the request. The role check enforces *which* roles are needed, not *who* the caller is. Add SSO/Cognito before real use.
- RUL is a linear trend extrapolation to a site alarm limit. It is not validated, may be optimistic for accelerating degradation, and is computed on simulated data. The risk score is uncalibrated.
- Fault signatures are a small rule set in `fixtures/fault_modes.json`, not a trained classifier.
- The machine view is a 2D SVG schematic, not a 3D model. Parts are keyed by `visualization_id`, so a GLB viewer can reuse the same ids.
- Procurement, CMMS and inventory integrations are stubs.
- The frontend TypeScript types are hand-mirrored from the Pydantic schemas.
