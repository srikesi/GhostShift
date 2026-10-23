# Workstream 3: Organizer requirements and data

**Prompt to give the agent:**

> You are finishing the GhostShift hackathon project (AWS Agentic AI Hackathon, Track 2). Pull `main`, then read `README.md`, `docs/workstreams/README.md` (ownership and git rules: follow them exactly) and this file, `docs/workstreams/3-requirements-data.md`. Complete workstream 3 and push to `main` in small, verified commits. Only edit files your workstream owns. Ask the human for the official hackathon requirements, starter repository and datasets if you can't find them.

## Why
The organizers announce final technical requirements, required AWS services and datasets at the event. GhostShift must meet them without breaking the working demo.

## Goal
Map every official requirement to a concrete change. Implement the data and AWS-source requirements, and route the rest to the right workstream.

## Build
1. **Requirements map first, within the first hour.** Read the official requirements and starter code, and check each service's official documentation. Write `docs/requirements-map.md`: one row per requirement, with status, owning workstream (1–4), files and notes.
   - Push it early.
   - For each requirement owned by another stream, add an entry to that stream's `docs/workstreams/inbox-<n>.md`.
2. **Sensor coverage (done; optional extension).** Both demo machines already carry temperature, vibration, energy (`spindle_power`, `package_power`) and lube monitoring (`way_lube_pressure`, `way_lube_level`, `separator_dp`, `oil_level`), all simulated and generated from separate seeds so the original channels are unchanged. Optional: add `spindle_lube_flow` (oil-air lubrication to the front bearing) that falls slightly before the bearing degrades, as a supporting condition in `FM-VMC-SPB-WEAR`. If you do, keep the story timing (VMC-07 flagged around sample 170, High around 174, Urgent around 226) and update the tests, and ask workstream 4 to update the README demo script if numbers shift.
3. **Industrial Machine Downtime Prediction dataset (Kaggle).** This is the best real-style dataset for our spindle story. Ask the human to download it; Kaggle needs a login. Never commit the raw file.
   - From memory, it has per-machine dates, spindle vibration, spindle bearing temperature, coolant and hydraulic-oil temperature and pressures, voltage, torque and a downtime label. **Verify the actual columns first.**
   - Write an adapter that maps each machine ID to a GhostShift machine and converts units.
   - Derive power (energy) where possible, with `derived` provenance.
   - Treat hydraulic/lube oil signals as the lube monitor.
   - Keep the downtime label out of agent inputs; it's ground truth only.
   - Add a small evaluation script that reports how early GhostShift flags each downtime event (lead time) and how many false alarms it raises. Judges will ask how well it works.
4. **AI4I 2020, real file (UCI, CC BY 4.0, also mirrored on Kaggle).** The loader `integrations/ai4i.py` exists but has only run on synthetic sample rows. Ask the human before downloading the file, then set `GHOSTSHIFT_AI4I_PATH`. Add the dataset's documented failure rules as fault patterns for `ai4i_milling`:
   - heat-dissipation failure (air–process temperature gap with low speed)
   - power failure (torque × speed outside the allowed power band)
   - overstrain (tool wear × torque)
   - tool-wear failure

   Compute power and strain as `derived` channels in the adapter. Evaluate detections against the labels in the same evaluation script.
5. **AWS data sources.** Implement these if the organizers require them. The AWS samples *Scale Predictive Maintenance POC* (IoT SiteWise) and *Amazon SageMaker Predictive Maintenance* (Kinesis, Glue) show the expected shape. Implement each source as a `TelemetryProvider` adapter in `backend/ghostshift/integrations/`:
   - Keep the client lazy, so there is no I/O at import or construction.
   - Map errors to `ProviderError`, give it `health()`, and use correct provenance (`measured` or `simulated`).
   - Register it in `build_container()` behind a setting in your `config.py` section.
   - Follow `.claude/skills/add-integration` and `.claude/skills/add-dataset`.
   - Skip SageMaker model training unless it is required; it costs hours and the rules-based detection already works.
6. **General dataset rules.**
   - Document which fields exist and which are missing.
   - If the data is not a run-to-failure trajectory, the time-to-limit estimate should say "not estimated". Don't force a number.
   - Raw datasets stay out of git (add their paths to `.gitignore` through workstream 4's inbox). Keep a few synthetic rows in `backend/tests/data/` for tests.
7. **New machines.** If the data implies a different machine type:
   - Add components, sensor limits and fault patterns in `fixtures/`.
   - Add a schematic in `frontend/src/features/assembly/drawings.tsx`, keyed by `visualization_id` (the generic fallback works until then).
   - Add a scenario so it can be replayed.
8. **Contracts.** If you add fields to machine, telemetry or reference schemas, or to routes in `api/routes.py`, update only the matching interfaces in `frontend/src/api/types.ts` and `client.ts`.
9. **Keep the demo intact.** VMC-07 and CMP-02 and their stories must keep working as described in `README.md`.

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
- The evaluation script runs on each real dataset available, and its results (lead time, false alarms) are recorded in `docs/data.md`.
- `docs/requirements-map.md` is complete, and `docs/data.md` documents every source and its gaps.
