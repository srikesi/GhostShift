# Workstream 3: Organizer requirements and data

**Prompt to give the agent:**

> You are finishing the Faultzy hackathon project (AWS Agentic AI Hackathon, Track 2). Pull `main`, then read `README.md`, `docs/workstreams/README.md` (ownership and git rules: follow them exactly) and this file, `docs/workstreams/3-requirements-data.md`. Complete workstream 3 and push to `main` in small, verified commits. Only edit files your workstream owns. Ask the human for the official hackathon requirements, starter repository and datasets if you can't find them.

## Why
The organizers announce final technical requirements, required AWS services and datasets at the event. Faultzy must meet them without breaking the working demo.

## Goal
Map every official requirement to a concrete change. Implement the data and AWS-source requirements, and route the rest to the right workstream.

## Build
1. **Requirements map first, within the first hour.** Read the official requirements and starter code, and check each service's official documentation. Write `docs/requirements-map.md`: one row per requirement, with status, owning workstream (1–4), files and notes.
   - Push it early.
   - For each requirement owned by another stream, add an entry to that stream's `docs/workstreams/inbox-<n>.md`.
2. **AWS data sources.** If required (for example IoT SiteWise, Timestream, S3, Kinesis or IoT Core), implement each as a `TelemetryProvider` adapter in `backend/faultzy/integrations/`.
   - Keep the client lazy, so there is no I/O at import or construction.
   - Map errors to `ProviderError`, give it `health()`, and use correct provenance (`measured` or `simulated`).
   - Register it in `build_container()` behind a setting in your `config.py` section.
   - Follow `.claude/skills/add-integration` and `.claude/skills/add-dataset`.
3. **Datasets.** Load the organizer data, or the real AI4I 2020 CSV if allowed, through an adapter.
   - Document which fields exist and which are missing.
   - Keep ground-truth labels out of agent inputs.
   - If the data is not a run-to-failure trajectory, the time-to-limit estimate should say "not estimated". Don't force a number.
4. **New machines.** If the data implies a different machine type:
   - Add components, sensor limits and fault patterns in `fixtures/`.
   - Add a schematic in `frontend/src/features/assembly/drawings.tsx`, keyed by `visualization_id` (the generic fallback works until then).
   - Add a scenario so it can be replayed.
5. **Contracts.** If you add fields to machine, telemetry or reference schemas, or to routes in `api/routes.py`, update only the matching interfaces in `frontend/src/api/types.ts` and `client.ts`.
6. **Keep the demo intact.** VMC-07 and CMP-02 and their stories must keep working exactly as in `README.md`.

## Verify before declaring done
- New tests in `backend/tests/test_data_*.py` for each adapter, with AWS calls mocked (a fake client or botocore Stubber):
  - normalization and unit conversion
  - provenance
  - missing fields
  - the not-configured state
  - errors
- A test that each new machine runs through `orchestrator.run()`.
- `make check` is green, and `make demo-smoke` passes in demo mode.
- With credentials, `GET /api/health` shows each new source as configured. The dashboard shows the new machine and its charts.
- `docs/requirements-map.md` is complete, and `docs/data.md` documents every source and its gaps.
