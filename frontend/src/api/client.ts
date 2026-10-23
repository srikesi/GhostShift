import type {
  AutonomySettings,
  BriefingResponse,
  DecisionRequest,
  HealthResponse,
  IncidentView,
  InspectionView,
  MachineDetail,
  MachineSummary,
  ProposedAction,
  ReplayResponse,
  TelemetryResponse,
  WorkflowRun,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new ApiError(0, "network_error", "GhostShift API is unreachable. Is the backend running on :8000?");
  }
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const err = body?.error ?? {};
    throw new ApiError(res.status, err.code ?? "http_error", err.message ?? res.statusText, err.details);
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  machines: () => request<MachineSummary[]>("/api/machines"),
  machine: (id: string) => request<MachineDetail>(`/api/machines/${id}`),
  telemetry: (id: string) => request<TelemetryResponse>(`/api/machines/${id}/telemetry`),
  replay: (id: string, action: "reset" | "advance" | "seek" | "to_end", opts: { steps?: number; cursor?: number } = {}) =>
    post<ReplayResponse>(`/api/machines/${id}/replay`, { action, ...opts }),
  runWorkflow: (id: string) => post<WorkflowRun>(`/api/machines/${id}/workflow`),
  incidents: (machineId?: string) =>
    request<IncidentView[]>(`/api/incidents${machineId ? `?machine_id=${encodeURIComponent(machineId)}` : ""}`),
  incident: (id: string) => request<IncidentView>(`/api/incidents/${id}`),
  briefing: (id: string) => request<BriefingResponse>(`/api/incidents/${id}/briefing`),
  decide: (actionId: string, body: DecisionRequest) => post<ProposedAction>(`/api/actions/${actionId}/decision`, body),
  execute: (actionId: string) => post<ProposedAction>(`/api/actions/${actionId}/execute`),
  inspect: (token: string) => request<InspectionView>(`/api/inspect/${encodeURIComponent(token)}`),
  inspectBriefing: (token: string) => request<BriefingResponse>(`/api/inspect/${encodeURIComponent(token)}/briefing`),
  resetDemo: () => post<void>("/api/demo/reset"),
  autonomy: () => request<AutonomySettings>("/api/autonomy"),
  setAutonomy: (level: AutonomySettings["level"]) =>
    request<AutonomySettings>("/api/autonomy", { method: "PUT", body: JSON.stringify({ level }) }),
};
