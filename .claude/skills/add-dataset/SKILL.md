---
name: add-dataset
description: Load a new telemetry dataset or machine (e.g. AI4I 2020, CMAPSS, a hackathon-provided CSV/S3/Timestream source) into Faultzy through a telemetry adapter, keeping raw, derived and simulated data separate.
---

# Add a dataset or machine

## Purpose
Feed new data to the agents through the normalized `TelemetryWindow` contract without coupling agents to a CSV schema, and be explicit about what the data cannot support.

## When to use
- A real or organizer-supplied dataset should drive diagnostics.
- Adding another demo machine/scenario.

## Inspect first
- `backend/faultzy/schemas/telemetry.py` (`TelemetryPoint`, `TelemetryWindow`) and `schemas/machine.py` (`Machine`, `SensorDefinition`, `SensorLimits`).
- `backend/faultzy/integrations/ai4i.py` — reference adapter: column map, unit conversion, synthesized timestamps, `unavailable_fields`, labels kept out of agent inputs.
- `backend/faultzy/integrations/telemetry_fixture.py` — `CompositeTelemetryProvider.add()` routing.
- `backend/faultzy/fixtures/{machines,fault_modes,site}.json` — for fixture-style machines.

## Checklist
1. Inventory the dataset's columns, units, sampling, timestamps and labels. Write down which Faultzy sensors it **cannot** provide.
2. Write an adapter implementing `TelemetryProvider` (`machine_ids`, `length`, `window`, `health`). Convert units; map to stable sensor ids.
3. Set provenance truthfully: `measured` for real observations, `simulated` for generated data or synthesized timestamps. Fill `unavailable_fields`.
4. Keep ground-truth labels (failure flags, RUL targets) out of `TelemetryPoint.values`; expose them separately for evaluation only.
5. Provide a `Machine` (components with `visualization_id`, sensors with limits + limit provenance) and a `Scenario` (baseline window, initial/jump cursor). Register via `ReferenceData.register_machine` and `telemetry.add`.
6. Add fault signatures to `fault_modes.json` only if they are defensible for this machine type; otherwise diagnostics reports an unclassified deviation.
7. If the data is not a run-to-failure trajectory, expect prognostics to report RUL as not supportable — do not force a number.
8. For a drawing, add a schematic in `frontend/src/features/assembly/drawings.tsx` keyed by `visualization_id`; otherwise the generic component grid is used.
9. Large raw datasets stay out of git (`.gitignore`); ship a small synthetic sample in `tests/data/` for tests.

## Tests required before done
- Adapter test on a small sample: normalization, unit conversion, provenance, `unavailable_fields`, labels not leaked.
- Diagnostics runs on the new machine without error (`orchestrator.run(machine_id)`).
- `GET /api/machines` lists it; dashboard renders it (generic drawing if none).
- `make test`, `make typecheck`, `make build` pass.
