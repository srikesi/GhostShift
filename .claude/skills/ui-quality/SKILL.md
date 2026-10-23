---
name: ui-quality
description: Build or review Faultzy frontend UI (dashboard panels, mobile inspection page, charts, assembly drawings) to the product's industrial design standard — graphite/off-white, status-only color, honest provenance, responsive and accessible.
---

# Faultzy UI quality

## Purpose
Keep the interface credible for an industrial operations team: dense but legible, every simulated value identifiable, color reserved for status.

## When to use
- Adding or changing any screen, panel, chart or drawing.
- Before a demo or a screenshot for the pitch.

## Inspect first
- `frontend/src/styles/tokens.css` (palette, type scale, spacing) and `global.css` (panel, pill, tag, notice, table primitives).
- `frontend/src/components/ui.tsx` — `SeverityPill`, `PriorityPill`, `SimTag`, `ProviderNote`, `Panel`, `SafetyNotice`, `Icon`.
- `frontend/src/features/telemetry/SensorChart.tsx` and `features/assembly/*` for visualization patterns.

## Rules
- Palette: graphite + warm off-white, light only (no dark mode). Amber/red only for watch/warning/critical; normal parts and sensors stay neutral. No gradients, glow, glassmorphism or emoji.
- Typography: IBM Plex Sans for text, IBM Plex Mono for ids, numbers and units (bundled via @fontsource, works offline). Icons: lucide-react only.
- Plain words. Write "normal", "time to danger limit", "priority", "+84% vs normal". Do not show σ, z-scores, "RUL", "deterministic", "heuristic", "uncalibrated" or "provenance" in the main UI; that detail belongs in the collapsed *How Faultzy decided* section.
- Two scales, never mixed: sensor/part condition = Normal/Watch/Warning/Critical (`SeverityPill`); problem urgency = Low/Medium/High/Urgent (`PriorityPill`). When a machine has an open problem, show its priority, not its sensor severity.
- Provenance without clutter: the top bar states demo/live mode. Use `SimTag` only on outputs a viewer could mistake for real (texts, orders, stock, the sensor panel). Use `ProviderNote` only when a live provider was used, fell back or failed; built-in rules show nothing.
- Safety copy: never imply a button isolates or makes equipment safe. Approval "records a decision"; ordering and dispatch are tagged Simulated.
- One idea per panel. If text repeats something shown elsewhere, cut it. Prefer a number with units next to its normal value over a sentence.
- No animation except state changes the user caused. No pulsing, no entry transitions.

## Checklist
1. Reuse primitives; add tokens rather than raw colors.
2. Laptop (1440 and 1024 wide) and phone (375 wide): no horizontal page scroll; tables wrap in `.table-scroll`.
3. Keyboard: interactive SVG parts and controls are focusable with visible focus; buttons are `<button>`.
4. Charts have `role="img"` + `aria-label` summaries; status is never color-only (text label in pills).
5. Empty, loading, error and provider-failure states are designed, not blank.

## Verification required before done
- `make typecheck` and `make build` pass.
- Run the app (`make dev`), play the VMC-07 replay to the end, and check the dashboard at 1440/1024 and `/m/<token>` at 375 width: `document.documentElement.scrollWidth === clientWidth`.
- Count words on the incident screen (`document.querySelector('main').innerText.split(/\s+/).length`); it should stay around 600 or below.
- Screenshot the problem column and mobile view; confirm the Simulated tags are on texts and orders and nothing implies physical isolation.
