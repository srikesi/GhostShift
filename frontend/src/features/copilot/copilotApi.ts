import { post } from "../../api/client";
import type { ProviderInfo, StageStatus } from "../../api/types";

/** Mirrors backend/ghostshift/schemas/copilot.py. */
export interface ChatTurn {
  role: "user" | "assistant";
  text: string;
}

export interface ToolCallRecord {
  name: string;
  agent: string;
  input: Record<string, unknown>;
  ok: boolean;
  summary: string;
  duration_ms: number;
}

export interface CopilotAnswer {
  machine_id: string;
  incident_id: string | null;
  answer: string;
  tool_calls: ToolCallRecord[];
  status: StageStatus;
  provider: ProviderInfo;
  built_in: boolean;
  error: string | null;
  suggested_questions: string[];
}

export const askCopilot = (body: { machine_id: string; incident_id?: string | null; question: string; history: ChatTurn[] }) =>
  post<CopilotAnswer>("/api/copilot/ask", body);
