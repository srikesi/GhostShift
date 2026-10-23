# How Faultzy fits the brief

**The brief:** a multi-agent system that ingests temperature, energy, vibration and lube monitor data to predict equipment failure, estimate useful life, auto-order parts and schedule maintenance.

Keep pitch claims to what the build actually does. Update the **Today** column as workstreams land.

| Capability | How Faultzy does it | Today | After workstreams |
|---|---|---|---|
| **Multi-agent** | Five specialist agents with typed inputs and outputs: diagnostics, prognostics, safety supervisor, maintenance & supply, narrative. An orchestrator runs them in order, with timeouts, failure handling and a step log. | Yes. The specialists are rule- and statistics-based; an LLM only rewords the summary. | WS1 adds a Bedrock supervisor agent that delegates to the specialists as tools and answers questions. That's the "agentic" part judges look for. |
| **Ingests temperature** | Bearing temperature (VMC-07); discharge and oil temperature (CMP-02). | Yes (simulated data). | Plus real datasets (WS3). |
| **Ingests vibration** | Spindle vibration (VMC-07); airend vibration (CMP-02). | Yes (simulated). | Plus real datasets (WS3). |
| **Ingests energy** | Motor current only, which stands in for energy use. | Partial | WS3 adds power (kW) sensors, and derives power from torque × speed in the real datasets. |
| **Ingests lube monitor** | The way-lube unit exists as a part but has no sensors. | No | WS3 adds lube pressure, level and filter sensors, and uses hydraulic/lube oil signals from the downtime dataset. |
| **Predict failure** | Spots readings moving out of their normal range, matches known fault patterns, and checks alarm limits. Flags problems hours before the alarm limit is crossed. | Yes | WS3 measures how early it flags real downtime events, and how many false alarms it raises. |
| **Estimate useful life** | Time to the danger limit from the recent trend, given as a range. Shown only when the trend is clear. Schedule-based service due for every part. | Yes. A simple trend estimate, not validated. | Same method. Quote it as an estimate. |
| **Auto-order parts** | Picks the best-matching part (fit, stock, lead time), drafts the requisition, and sends it once a supervisor approves. | Drafted automatically; sending is human-approved and **simulated**. | WS3/WS2 could connect a real ERP or catalog if the organizers provide one. Keep human approval: say "auto-drafted, one-click approve". |
| **Schedule maintenance** | Picks the earliest planned downtime that fits the part lead time and job length, and warns when that is too late. Drafts the work order and texts the technician a link to a phone page with the part highlighted. | Proposed and drafted automatically; dispatch is human-approved and **simulated**. Texts are simulated unless Twilio is configured (WS2). | WS2: real texts and a hosted URL. |

## One-paragraph description (accurate today)

Faultzy is a team of specialist agents for maintenance. It watches machine sensors and flags a problem hours before an alarm limit is reached. It explains which readings moved and which fault they point to, and estimates how long until the danger limit. It then picks the replacement part, finds the next planned downtime, and drafts the purchase order and work order. A safety supervisor in code decides the priority and requires a human to approve anything that orders parts or starts physical work. The technician gets a text with a link that shows the machine and the part to replace. In this demo, sensor data, stock, orders and texts are simulated.

Once workstreams 1–3 land, change it to: "...a Bedrock-powered supervisor agent coordinates specialist agents over temperature, energy, vibration and lube data..."

## Don't claim
- That the life estimate is validated or ML-based. It's a trend estimate on simulated data.
- That parts are ordered or work is dispatched without a person approving.
- That the app makes equipment safe or isolates it.
