---
name: add-integration
description: Add or replace an external provider in Faultzy (an AWS service, Twilio, ElevenLabs, a CMMS/ERP, a hackathon-supplied API or SDK) behind an existing or new provider interface, without breaking the offline demo.
---

# Add an integration to Faultzy

## Purpose
Connect a real external service through an isolated adapter so agents, orchestrator and UI do not change, and `FAULTZY_MODE=demo` keeps working offline.

## When to use
- Organizers announce a required AWS service, SDK, API or starter repo.
- Swapping a stub (SMS, voice, procurement, work orders, telemetry, LLM) for a real system.

## Inspect first
- `backend/faultzy/integrations/base.py` — Protocols, `ProviderError`/`ProviderNotConfigured`, `ProviderHealth`, `info()`.
- `backend/faultzy/container.py` — `choose_*` functions; the mode/fallback contract in the module docstring.
- An existing adapter of the same shape: `bedrock.py` (boto3, lazy client), `sms.py` (httpx + bounded retry), `voice.py`.
- `backend/faultzy/config.py` — add settings here; secrets as `SecretStr`.
- The official docs and any hackathon starter code for the service. Confirm region, model/profile ids, IAM actions and quotas in the real account before choosing defaults.

## Checklist
1. If no Protocol fits, add one to `integrations/base.py` (small, typed, returns dataclasses/contracts, raises `ProviderError(retryable=...)`).
2. Create `integrations/<service>.py`. Constructor stores config only — **no network or credential lookup at import or construction**. Create clients lazily.
3. Map the service's errors to `ProviderError` with `retryable` set correctly; bound retries (`*_max_attempts` setting) and timeouts.
4. Implement `health(probe=False)`: report `configured` without network; only call the service when `probe=True`.
5. Add settings to `config.py` and placeholders to `.env.example` (never real values). Keep secrets server-side only.
6. Wire it in `container.py` following the contract: `demo` → stub; `auto` → real only if configured, else stub; `aws` → real even if misconfigured so failures surface.
7. Label results honestly: real calls use `ProviderKind.external`; simulated paths stay `stub`. Never turn a failure into a success-looking result.
8. If it performs an operational action (orders, dispatch, shutdown), route it through `ApprovalService.execute` — never call it directly from an agent or route.
9. Update README "Integration points" table.

## Tests required before done
- Unit test for the adapter with the network mocked (`httpx.MockTransport` or a fake boto3 client via `client_factory`): success, retryable failure (bounded), non-retryable failure, not-configured.
- Selection test in `tests/test_integrations.py` for demo/auto/aws.
- `make test` and `make typecheck` pass; `make demo-smoke` passes with `FAULTZY_MODE=demo`.
- `GET /api/health` lists the provider with correct `configured`/`real` flags.
