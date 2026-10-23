---
name: demo-readiness
description: Pre-demo checklist for Faultzy — verify the end-to-end story runs offline and with any live integrations, reset state, and prepare fallbacks before presenting to judges.
---

# Faultzy demo readiness

## Purpose
Make sure the 3-minute story works every time: normal → deviation → diagnosis with evidence → qualified RUL/risk → part + simulated requisition → safety tier + approval gate → SMS → mobile inspection with highlighted component.

## When to use
- Before any demo, recording or judging slot.
- After integrating a new service or changing agents.

## Inspect first
- `README.md` "Demo script" section.
- `GET /api/health` — mode and provider status.
- `.env` for the presenting machine (mode, Bedrock model id, Twilio opt-in number).

## Checklist
1. `make check` (tests + typecheck + build) is green.
2. Offline path: with `FAULTZY_MODE=demo`, `make dev`, then `make demo-smoke` → "Demo story verified".
3. Live path (if used): `make check-bedrock` succeeds; set `FAULTZY_MODE=auto` so a network failure falls back visibly instead of breaking the demo. For Twilio, confirm `FAULTZY_DEMO_TECHNICIAN_PHONE` is the presenter's phone and send one test.
4. `FAULTZY_PUBLIC_BASE_URL` points to an address the phone can reach (LAN IP with `npm run dev -- --host`, or a tunnel). Open one SMS link on the phone.
5. Click **Reset demo** in the top bar. VMC-07 shows Normal at sample 120.
6. Rehearse: Play → auto-pause at detection (elevated) → Play → SMS at high → approve requisition → show 422 when approving work order without isolation attestation → open mobile view.
7. Rehearse the Autonomy demo in the README (Autopilot on → Play → "10 on its own · 0 by people" → only the lockout/tagout sign-off left). Turn Autopilot back off afterwards if the next demo needs the manual approval flow.
8. Have the fallback ready: if anything external fails, switch to `FAULTZY_MODE=demo` and restart the API (state is in-memory; restart = clean slate).

## Do not
- Do not claim simulated values are measured, or that the RUL is validated.
- Do not demonstrate a real purchase or real equipment action.

## Verification required before done
- `make demo-smoke` output pasted into the team channel with the mode used.
- Screenshot of the dashboard incident and the phone's inspection page.
