# Workstream 2: Deploy and live messaging

**Prompt to give the agent:**

> You are finishing the GhostShift hackathon project (AWS Agentic AI Hackathon, Track 2). Pull `main`, then read `README.md`, `docs/workstreams/README.md` (ownership and git rules: follow them exactly) and this file, `docs/workstreams/2-deploy-messaging.md`. Complete workstream 2 and push to `main` in small, verified commits. Only edit files your workstream owns. Ask the human before creating paid AWS resources, and before sending any SMS.

## Why
GhostShift only runs on a laptop today. Judges need a URL. The technician's text needs to reach a real phone, with a link that phone can open.

## Goal
Get a public HTTPS deployment, real Twilio texts to a configured phone, and optionally ElevenLabs voice, with a runbook anyone on the team can follow.

## Build
1. **Single container.** Write a multi-stage `Dockerfile` that runs `npm run build` and then installs the backend with uv. Run one uvicorn worker, because state is in memory. Set `GHOSTSHIFT_STATIC_DIR=/app/frontend/dist`; `api/static.py` already serves the SPA, including `/m/<token>`. Add a `.dockerignore`.
2. **Makefile targets:**
   - `docker-build` and `docker-run` (passes `.env`)
   - `web-lan`: Vite with `--host`, plus instructions to set `GHOSTSHIFT_PUBLIC_BASE_URL=http://<lan-ip>:5173` for testing with a phone on the same Wi-Fi
   - `deploy`
3. **AWS hosting.** Use the simplest option available in the workshop account: App Runner, ECS Fargate behind an ALB, or Lightsail containers, in that order of preference. Put scripts and templates in `deploy/`.
   - Use an HTTPS URL.
   - Supply secrets through environment variables or Secrets Manager, never baked into the image.
   - The task or instance role needs `bedrock:InvokeModel` on the model and profile that workstream 1 picks (read `docs/copilot.md` once it exists).
   - Set `GHOSTSHIFT_PUBLIC_BASE_URL` to the deployed URL.
4. **Access.** The hosted dashboard is public by default. Add a simple shared-passcode gate for `/` and `/api/*`, configured through an environment variable and implemented in `main.py`. Exempt `/api/health` and `/m/<token>` with `/api/inspect/*`, because the token already scopes those. Keep it off in local demo mode.
5. **Twilio live.** Test with `make text-me`, using `GHOSTSHIFT_MODE=auto`, `GHOSTSHIFT_SMS_PROVIDER=twilio`, the `TWILIO_*` values and `GHOSTSHIFT_DEMO_TECHNICIAN_PHONE`. Trial accounts can only text verified numbers, so document that. Confirm the link opens on the phone and shows the highlighted part.
6. **ElevenLabs (optional).** Test `GHOSTSHIFT_VOICE_PROVIDER=elevenlabs`. The phone page's "Spoken briefing" should play audio.
7. **Robustness.** Make the API restart-safe: a restart clears state, which is acceptable, but document it. Add a container health check on `/api/health`.

## Verify before declaring done
- New tests in `backend/tests/test_deploy_*.py`:
  - the passcode gate (blocked, allowed, exempt paths)
  - static serving inside the container layout
  - Twilio and ElevenLabs behaviour with mocked HTTP, for any new code
- `make check` is green. With `GHOSTSHIFT_MODE=demo`, `make demo-smoke` passes locally and against the deployed URL (`GHOSTSHIFT_API_URL=https://... make demo-smoke`).
- A real SMS arrives on the configured phone. Its link opens the technician view over HTTPS.
- `docs/deploy.md` is a step-by-step runbook covering build, deploy, environment variables, redeploy, rollback, cost notes and teardown.
