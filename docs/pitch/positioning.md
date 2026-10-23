# How Faultzy fits the brief

**The brief:** a multi-agent system that ingests temperature, energy, vibration and lube monitor data to predict equipment failure, estimate useful life, auto-order parts and schedule maintenance.

Keep pitch claims to what the build actually does. Update the **Today** column as workstreams land.

| Capability | How Faultzy does it | Today | After workstreams |
|---|---|---|---|
| **Multi-agent** | Five specialist agents with typed inputs and outputs: diagnostics, prognostics, safety supervisor, maintenance & supply, narrative. An orchestrator runs them in order, with timeouts, failure handling and a step log. | Yes. The specialists are rule- and statistics-based; an LLM only rewords the summary. | WS1 adds a Bedrock supervisor agent that delegates to the specialists as tools and answers questions. That's the "agentic" part judges look for. |
| **Ingests temperature** | Bearing temperature (VMC-07); discharge and oil temperature (CMP-02). | Yes (simulated data). | Plus real datasets (WS3). |
| **Ingests vibration** | Spindle vibration (VMC-07); airend vibration (CMP-02). | Yes (simulated). | Plus real datasets (WS3). |
| **Ingests energy** | Spindle power and compressor package power (kW), plus motor current. | Yes (simulated). | WS3 derives power from torque × speed in the real datasets. |
| **Ingests lube monitor** | Way-lube pressure and reservoir level (VMC-07); oil level and oil-separator pressure drop (CMP-02). | Yes (simulated). | WS3 adds hydraulic/lube oil signals from the downtime dataset. |
| **Predict failure** | Spots readings moving out of their normal range, matches known fault patterns, and checks alarm limits. Flags problems hours before the alarm limit is crossed. | Yes | WS3 measures how early it flags real downtime events, and how many false alarms it raises. |
| **Estimate useful life** | Time to the danger limit from the recent trend, given as a range. Shown only when the trend is clear. Schedule-based service due for every part. | Yes. A simple trend estimate, not validated. | Same method. Quote it as an estimate. |
| **Auto-order parts** | Picks the best-matching part (fit, stock, lead time) and drafts the requisition. With **Autopilot** on, it places the order itself when priority is High or Urgent, the cost is within the limit, and the part is in stock or arrives before the earliest limit. Otherwise a supervisor approves. | Yes with Autopilot (the order is **simulated**). Off by default. | WS3/WS2 could connect a real ERP or catalog. |
| **Schedule maintenance** | Picks the earliest planned downtime that fits the part lead time and job length, and warns when that is too late. Drafts the work order and texts the technician a link to a phone page with the part highlighted. | Proposed and drafted automatically; dispatch is human-approved and **simulated**. Texts are simulated unless Twilio is configured (WS2). | WS2: real texts and a hosted URL. |

## How autonomous is it?

| Step | Who does it |
|---|---|
| Watch temperature, energy, vibration and lube sensors; spot and diagnose a fault | Faultzy |
| Estimate time to the danger limit; set priority | Faultzy |
| Pick the part, draft the order, propose the downtime slot, draft the work order | Faultzy |
| Text the technician the link | Faultzy |
| Place the parts order | **Autopilot** (within policy), otherwise a supervisor |
| Release physical work (lockout/tagout) | **Always a supervisor**, by design |

Demo it with the "Autonomy demo" in the README. The *What Faultzy did* timeline counts the steps Faultzy took on its own against those taken by people (10 vs 0 on the VMC-07 run).

## One-paragraph description (accurate today)

Faultzy is a team of specialist agents for maintenance. It watches temperature, energy, vibration and lube sensors and flags a problem hours before an alarm limit is reached. It explains which readings moved and which fault they point to, and estimates how long until the danger limit. It then picks the replacement part, finds the next planned downtime, drafts the work order and, on Autopilot, orders the part itself within a spending policy. A safety supervisor in code sets the priority, and physical work always waits for a supervisor's lockout/tagout sign-off. The technician gets a text with a link that shows the machine and the part to replace. In this demo, sensor data, stock, orders and texts are simulated.

Once workstreams 1–3 land, change it to: "...a Bedrock-powered supervisor agent coordinates specialist agents over temperature, energy, vibration and lube data..."

## Don't claim
- That the life estimate is validated or ML-based. It's a trend estimate on simulated data.
- That work is dispatched without a person approving, or that parts are ordered without limits. Autopilot orders only within its policy.
- That the app makes equipment safe or isolates it.
