# Parallel workstreams

Four agents, on different computers, finish Faultzy at the same time and push straight to `main`. Each workstream **owns** a set of files. Owning a file means you are the only one who edits it. That rule, plus the git protocol below, is what keeps the streams from overwriting each other.

| # | Workstream | Prompt |
|---|---|---|
| 1 | Agentic copilot (Bedrock tool use) | [1-agentic-copilot.md](1-agentic-copilot.md) |
| 2 | Deploy and live messaging (AWS hosting, Twilio, ElevenLabs) | [2-deploy-messaging.md](2-deploy-messaging.md) |
| 3 | Organizer requirements and data | [3-requirements-data.md](3-requirements-data.md) |
| 4 | Demo quality, tests and pitch | [4-demo-qa-pitch.md](4-demo-qa-pitch.md) |

## File ownership

| Path | Owner |
|---|---|
| `backend/faultzy/agents/**`, `backend/faultzy/orchestrator.py`, `backend/faultzy/approvals.py` | 1 |
| `backend/faultzy/schemas/agents.py`, `schemas/workflow.py`, `schemas/common.py` | 1 |
| `backend/faultzy/integrations/bedrock.py`, `backend/faultzy/api/copilot_routes.py`, `backend/faultzy/api/autonomy_routes.py`, `backend/agentcore/**` (new) | 1 |
| `container.py`: `choose_llm()` only | 1 |
| `backend/pyproject.toml`, `backend/uv.lock` | 1 (others: request in inbox) |
| `frontend/src/features/copilot/**`, `backend/faultzy/knowledge/**` (new) | 1 |
| `backend/faultzy/main.py`, `backend/faultzy/api/static.py`, `backend/faultzy/state.py` | 2 |
| `backend/faultzy/integrations/sms.py`, `integrations/voice.py`, `backend/scripts/text_me.py` | 2 |
| `container.py`: `choose_sms()`, `choose_voice()` | 2 |
| `deploy/**`, `Dockerfile*`, `.dockerignore`, `Makefile` | 2 |
| `backend/faultzy/integrations/telemetry_fixture.py`, `integrations/ai4i.py`, `integrations/supply.py`, any new data adapter | 3 |
| `backend/faultzy/reference.py`, `backend/faultzy/fixtures/**`, `backend/scripts/generate_fixtures.py` | 3 |
| `backend/faultzy/schemas/machine.py`, `schemas/telemetry.py`, `schemas/reference.py`, `backend/faultzy/api/routes.py` | 3 |
| `container.py`: `build_container()` body | 3 |
| `frontend/src/features/assembly/**` | 3 |
| Everything else in `frontend/` (pages, components, styles, lib, other features, `package.json`, lockfile, configs) | 4 |
| `README.md`, `docs/DECISIONS.md`, `docs/pitch/**`, `.github/**`, `.claude/skills/**` | 4 |

Shared files, where each stream edits only its own part:
- `backend/faultzy/config.py` and `.env.example`: add settings only under your workstream's marked section.
- `frontend/src/api/types.ts` and `frontend/src/api/client.ts`: edit only the interfaces/functions that mirror schemas or routes you own. New copilot types and calls go in `features/copilot/`.
- `backend/tests/`: put new tests in **new files** named for your stream (`test_copilot_*.py`, `test_deploy_*.py`, `test_data_*.py`). Edit an existing test only when your own change makes it outdated.
- `docs/`: write your documentation in your own file (`docs/copilot.md`, `docs/deploy.md`, `docs/data.md`). Workstream 4 links them from the README.

Need a change in a file you don't own? Don't edit it. Add a dated entry to the owner's inbox (`docs/workstreams/inbox-<n>.md`) and push. Owners check their inbox each time they pull. If two inbox entries conflict on rebase, keep both.

## Git protocol (everyone)

1. Start: `git pull --rebase origin main`, then `make setup`.
2. Make small commits that each leave the app working. Don't let changes pile up.
3. Before every push:
   - Run `git pull --rebase origin main`.
   - Run `make check`. If you touched backend behaviour, also run `make api`, then `make demo-smoke`.
   - Push with `git push origin main`.
4. Never force-push, and never rewrite history that is already pushed.
5. If `uv.lock` or `package-lock.json` conflicts during a rebase, take the upstream version, then rerun `uv lock` (in `backend/`) or `npm install` (in `frontend/`), and commit.
6. Commit messages are plain, with no `Co-Authored-By` trailer for any AI.
7. Never commit `.env`, credentials, phone numbers or account IDs.

## Invariants (all streams)

- `FAULTZY_MODE=demo` must keep working offline, with no credentials.
- Safety tiers and approval gates stay deterministic code. No model output can change them or execute an action.
- Follow `.claude/skills/ui-quality/SKILL.md` for any UI: plain words, the light graphite theme, no dark mode, minimal animation.
- Label anything simulated. Never present simulated output as real.
