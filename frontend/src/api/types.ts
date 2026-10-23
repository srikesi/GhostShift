// TypeScript mirrors of the backend Pydantic contracts (backend/faultzy/schemas).
// Keep in sync when a schema changes; the backend is the source of truth.

export type Severity = "normal" | "watch" | "warning" | "critical";
export type RiskTier = "routine" | "elevated" | "high" | "critical";
export type DataSource = "measured" | "simulated" | "derived" | "fixture" | "external" | "llm";
export type StageStatus = "success" | "deterministic_fallback" | "provider_failure" | "invalid_result" | "skipped";
export type ProviderKind = "deterministic" | "stub" | "external";
export type ApproverRole = "maintenance_supervisor" | "operations_manager";
export type ActionStatus =
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "completed_simulated"
  | "completed"
  | "failed";
export type RecordStatus = "draft" | "awaiting_approval" | "submitted_simulated" | "submitted" | "rejected";

export interface Provenance {
  source: DataSource;
  detail: string;
  upstream_source: DataSource | null;
}

export interface ProviderInfo {
  name: string;
  kind: ProviderKind;
  real: boolean;
  model_id: string | null;
}

export interface ProviderHealth {
  capability: string;
  provider: ProviderInfo;
  configured: boolean;
  available: boolean | null;
  detail: string;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  mode: "demo" | "aws" | "auto";
  providers: ProviderHealth[];
  simulated_capabilities: string[];
}

export interface SensorLimits {
  direction: "above" | "below";
  alert: number | null;
  danger: number | null;
  provenance: Provenance;
}

export interface SensorDefinition {
  id: string;
  name: string;
  unit: string;
  component_id: string;
  role: "health" | "context";
  sample_interval_s: number;
  limits: SensorLimits | null;
  provenance: Provenance;
}

export interface Component {
  id: string;
  name: string;
  type: string;
  visualization_id: string;
  criticality: string;
  description: string;
  maintenance: { last_service_at: string; service_interval_hours: number; provenance: Provenance };
}

export interface Machine {
  id: string;
  display_name: string;
  machine_type: string;
  model: string;
  drawing: string;
  context: { site: string; line: string; shift_pattern: string; duty: string };
  components: Component[];
  sensors: SensorDefinition[];
  provenance: Provenance;
}

export interface ComponentRulEstimate {
  value_hours: number | null;
  lower_hours: number | null;
  upper_hours: number | null;
  unit: string;
  method: string;
  supportable: boolean;
  basis_note: string;
  provenance: Provenance;
}

export interface ComponentHealth {
  component_id: string;
  status: Severity;
  health_score: number | null;
  basis: "sensor" | "interval_only";
  summary: string;
  rul: ComponentRulEstimate | null;
  remaining_service_interval: ComponentRulEstimate;
}

export interface MachineSummary {
  id: string;
  display_name: string;
  machine_type: string;
  model: string;
  site: string;
  line: string;
  status: Severity;
  status_note: string;
  open_incident_id: string | null;
  open_incident_tier: RiskTier | null;
  replay_cursor: number;
  replay_length: number;
}

export interface Baseline {
  start_index: number;
  end_index: number;
  mean: number;
  std: number;
  n: number;
}

export interface SensorAssessment {
  sensor_id: string;
  sensor_name: string;
  component_id: string;
  unit: string;
  role: string;
  baseline: Baseline;
  recent_mean: number;
  current_value: number;
  latest_value: number;
  z_score: number;
  pct_change: number;
  slope_per_hour: number;
  limit_state: "normal" | "alert" | "danger" | "no_limits";
  alert_limit: number | null;
  danger_limit: number | null;
  anomalous: boolean;
  severity: Severity;
  missing_points: number;
}

export interface EvidenceRef {
  id: string;
  sensor_id: string;
  start_index: number;
  end_index: number;
  start_time: string;
  end_time: string;
  description: string;
}

export interface Anomaly {
  sensor_id: string;
  component_id: string;
  severity: Severity;
  description: string;
  evidence_id: string;
}

export interface FaultHypothesis {
  fault_mode_id: string;
  name: string;
  component_id: string;
  signature_sensor_ids: string[];
  confidence: number;
  confidence_method: string;
  matched_conditions: string[];
  unmatched_conditions: string[];
  contradicting_conditions: string[];
}

export interface DiagnosticsResult {
  machine_id: string;
  analyzed_start_index: number;
  analyzed_end_index: number;
  severity: Severity;
  sensors: SensorAssessment[];
  anomalies: Anomaly[];
  hypotheses: FaultHypothesis[];
  evidence: EvidenceRef[];
  warnings: string[];
  method: string;
  provenance: Provenance;
}

export interface MachineDetail {
  machine: Machine;
  summary: MachineSummary;
  screening: DiagnosticsResult;
  component_health: ComponentHealth[];
}

export interface TelemetryPoint {
  index: number;
  timestamp: string;
  values: Record<string, number | null>;
}

export interface TelemetryResponse {
  machine_id: string;
  cursor: number;
  length: number;
  baseline_start_index: number;
  baseline_end_index: number;
  window: {
    machine_id: string;
    sensor_ids: string[];
    points: TelemetryPoint[];
    provenance: Provenance;
    timestamp_provenance: Provenance;
    unavailable_fields: string[];
  };
  scenario_phases: { label: string; start_index: number; end_index: number; provenance: Provenance }[];
  detection_segments: { start_index: number; end_index: number; severity: Severity }[];
}

export interface ReplayResponse {
  machine_id: string;
  cursor: number;
  length: number;
  screening_severity: Severity;
  screening_note: string;
  triggered_run_id: string | null;
  triggered_incident_id: string | null;
}

export interface FailureRisk {
  score: number;
  band: string;
  horizon_hours: number;
  calibrated: boolean;
  definition: string;
}

export interface RulEstimate {
  component_id: string;
  sensor_id: string | null;
  supportable: boolean;
  value_hours: number | null;
  lower_hours: number | null;
  upper_hours: number | null;
  unit: string;
  threshold: number | null;
  method: string;
  confidence_note: string;
  limitations: string[];
  provenance: Provenance;
}

export interface PrognosticsResult {
  machine_id: string;
  affected_component_id: string | null;
  failure_risk: FailureRisk;
  rul: RulEstimate | null;
  component_health: ComponentHealth[];
  method: string;
  limitations: string[];
  provenance: Provenance;
}

export interface ApprovalPolicy {
  action_kind: "submit_requisition" | "dispatch_work_order";
  roles: ApproverRole[];
  requires_isolation_attestation: boolean;
  reason: string;
}

export interface SafetyAssessment {
  risk_tier: RiskTier;
  rationale: string[];
  escalation: string[];
  recommended_response: string;
  notify_technician: boolean;
  required_approvals: ApprovalPolicy[];
  safety_notices: string[];
  policy_version: string;
}

export interface PartCandidate {
  sku: string;
  description: string;
  manufacturer_part_number: string;
  unit_cost_usd: number | null;
  cost_provenance: Provenance;
  match_score: number;
  match_rationale: string[];
  availability: { on_hand: number | null; lead_time_days: number | null; location: string | null; provenance: Provenance };
}

export interface MaintenanceProposal {
  component_id: string;
  fault_mode_id: string | null;
  proposed_part: PartCandidate | null;
  alternatives: PartCandidate[];
  quantity: number;
  estimated_cost_usd: number | null;
  maintenance_window: {
    start: string;
    end: string;
    label: string;
    rationale: string;
    before_rul_lower_bound: boolean | null;
    provenance: Provenance;
  } | null;
  work_order: {
    title: string;
    machine_id: string;
    component_id: string;
    fault_mode_id: string | null;
    priority: string;
    tasks: { step: number; description: string; requires_qualified_person: boolean }[];
    estimated_duration_hours: number;
    required_skills: string[];
    safety_references: string[];
  };
  next_steps: string[];
  warnings: string[];
}

export interface IncidentNarrative {
  headline: string;
  summary: string;
  technician_brief: string;
  sms_key_finding: string;
}

export interface StageRecord {
  name: string;
  status: StageStatus;
  provider: ProviderInfo;
  started_at: string;
  duration_ms: number;
  attempts: number;
  error: string | null;
  fallback_reason: string | null;
  warnings: string[];
}

export interface WorkflowRun {
  id: string;
  machine_id: string;
  trigger: "manual" | "replay_monitor";
  mode: string;
  analyzed_start_index: number;
  analyzed_end_index: number;
  status: "completed" | "completed_no_incident" | "awaiting_approval" | "failed";
  stages: StageRecord[];
  incident_id: string | null;
  created_at: string;
  completed_at: string | null;
  error: string | null;
}

export interface ApprovalRecord {
  role: ApproverRole;
  decision: "pending" | "approved" | "rejected";
  decided_by: string | null;
  decided_at: string | null;
  note: string | null;
  automated: boolean;
}

export interface ProposedAction {
  id: string;
  incident_id: string;
  kind: "submit_requisition" | "dispatch_work_order";
  title: string;
  target_id: string;
  status: ActionStatus;
  approvals: ApprovalRecord[];
  requires_isolation_attestation: boolean;
  isolation_attested_by: string | null;
  external_reference: string | null;
  result_note: string | null;
  provider: ProviderInfo | null;
  created_at: string;
  updated_at: string;
}

export interface Requisition {
  id: string;
  incident_id: string;
  sku: string;
  description: string;
  quantity: number;
  estimated_cost_usd: number | null;
  status: RecordStatus;
  simulated: boolean;
  external_reference: string | null;
  created_at: string;
}

export interface WorkOrder {
  id: string;
  incident_id: string;
  machine_id: string;
  component_id: string;
  title: string;
  priority: string;
  status: RecordStatus;
  simulated: boolean;
  window_start: string | null;
  window_end: string | null;
  external_reference: string | null;
  created_at: string;
}

export interface Notification {
  id: string;
  incident_id: string;
  channel: "sms";
  recipient_label: string;
  to_masked: string;
  body: string;
  inspection_url: string;
  status: "simulated_sent" | "sent" | "failed" | "skipped";
  provider: ProviderInfo;
  attempts: number;
  error: string | null;
  external_id: string | null;
  created_at: string;
}

export interface Incident {
  id: string;
  machine_id: string;
  status: "open" | "closed";
  severity: Severity;
  affected_component_id: string | null;
  fault_mode_id: string | null;
  created_at: string;
  updated_at: string;
  run_ids: string[];
  diagnostics: DiagnosticsResult;
  prognostics: PrognosticsResult;
  safety: SafetyAssessment;
  maintenance: MaintenanceProposal | null;
  narrative: IncidentNarrative;
  narrative_provider: ProviderInfo;
  narrative_status: StageStatus;
  action_ids: string[];
  requisition_id: string | null;
  work_order_id: string | null;
  notification_ids: string[];
}

export interface IncidentView {
  incident: Incident;
  actions: ProposedAction[];
  requisition: Requisition | null;
  work_order: WorkOrder | null;
  notifications: Notification[];
  latest_run: WorkflowRun | null;
  activity: ActivityEvent[];
}

export interface ActivityEvent {
  id: string;
  incident_id: string;
  at: string;
  machine_time: string | null;
  actor: "faultzy" | "policy" | "person";
  actor_name: string;
  kind: string;
  text: string;
}

export interface AutonomySettings {
  level: "advise" | "autopilot";
  auto_order_limit_usd: number;
}

export interface InspectionView {
  incident: Incident;
  machine_name: string;
  machine_id: string;
  drawing: string;
  components: { component: Component; health: ComponentHealth | null }[];
  work_order: WorkOrder | null;
  expires_at: string;
}

export interface BriefingResponse {
  incident_id: string;
  text: string;
  audio_available: boolean;
  audio_url: string | null;
  provider: ProviderInfo;
  status: StageStatus;
  error: string | null;
}

export interface DecisionRequest {
  role: ApproverRole;
  approver_name: string;
  decision: "approve" | "reject";
  note?: string;
  isolation_attestation: boolean;
}
