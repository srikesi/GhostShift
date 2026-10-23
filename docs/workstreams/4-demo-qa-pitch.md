# Workstream 4: Demo quality, tests and pitch

**Prompt to give the agent:**

> You are finishing the Faultzy hackathon project (AWS Agentic AI Hackathon, Track 2). Pull `main`, then read `README.md`, `docs/workstreams/README.md` (ownership and git rules: follow them exactly) and this file, `docs/workstreams/4-demo-qa-pitch.md`. Complete workstream 4 and push to `main` in small, verified commits. Only edit files your workstream owns. Pull often: you integrate what the other three streams ship.

## Why
Judges see the product for about three minutes. It has to work every time, look credible, and the story has to be clear. Right now there are no frontend tests and no CI.

## Goal
Deliver a tested, polished frontend, CI on every push, and a pitch kit: demo script, slides outline, Q&A prep and a backup-video plan.

## Build
1. **CI.** Add `.github/workflows/ci.yml`. On every push to `main` it installs uv and Node, then runs `make check`. It also starts the API and runs `make demo-smoke`. Keep it fast. The workflow needs no secrets.
2. **Frontend tests.** Add Vitest and Testing Library as devDependencies; you own `frontend/package.json`. Cover:
   - the format helpers (`rulRange`, `fmtHours`, `vsNormal`)
   - `ComponentHealthTable` and `PartCard` rendering
   - the approval card's states (awaiting, approved, sent, rejected)
   - the phone page's error state for an expired link

   Add `npm test` and include it in `make check` (ask workstream 2 through its inbox to add it, since it owns the `Makefile`).
3. **UI QA pass.** Follow `.claude/skills/ui-quality/SKILL.md` on every screen:
   - Dashboard at 1440 and 1024 wide, and the phone view at 375 wide.
   - Empty, loading, API-down and provider-failure states. To see the failure states, run the API with `FAULTZY_MODE=aws` and no credentials.
   - Keyboard use, so focus is visible and the SVG parts are reachable.

   Fix what you own. Send the rest to the owners' inboxes. Don't touch `features/copilot/**` or `features/assembly/**`.
4. **Pitch kit** in `docs/pitch/`:
   - `demo-script.md`: a 3-minute, click-by-click script with what to say. Start from the README demo script, and add the copilot and the live text once streams 1 and 2 land.
   - `slides.md`: a slide outline covering problem, demo story, architecture diagram (Mermaid), the agentic design, safety (deterministic gates and human approval), AWS services used, what is real versus simulated, and what's next.
   - `qa.md`: likely judge questions with honest answers. Examples: how accurate is the time-to-limit; what is simulated; how does it scale; why can't the model override safety.
   - `backup-video.md`: a shot list for the team to record a backup demo.
5. **README.** Keep the root README accurate as the other streams land. Link `docs/copilot.md`, `docs/deploy.md`, `docs/data.md` and `docs/requirements-map.md` when they exist. Update "What is real and what is simulated".
6. **Final readiness.** Near the deadline, run `.claude/skills/demo-readiness` against the deployed URL, and record the results in `docs/pitch/readiness.md`.

## Verify before declaring done
- CI is green on `main`.
- `npm test` passes, and `make check` passes.
- No horizontal scroll at 1440, 1024 or 375 on any page.
- The demo script was rehearsed end to end on the deployed URL, with screenshots referenced in `docs/pitch/readiness.md`.
