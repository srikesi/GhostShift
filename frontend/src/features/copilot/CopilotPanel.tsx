import type { IncidentView } from "../../api/types";

/**
 * Slot for the agentic copilot UI (docs/workstreams/1-agentic-copilot.md).
 * Rendered at the bottom of the dashboard's right column. Renders nothing until built.
 * Keep copilot types and API calls inside features/copilot/.
 */
export function CopilotPanel(_props: { machineId: string; incident: IncidentView | null }) {
  return null;
}
