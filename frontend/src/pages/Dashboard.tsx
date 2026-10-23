import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type {
  AutonomySettings,
  DecisionRequest,
  DiagnosticsResult,
  HealthResponse,
  IncidentView,
  MachineDetail,
  MachineSummary,
  TelemetryResponse,
} from "../api/types";
import { Icon, Panel, PriorityPill, SeverityPill, Wordmark } from "../components/ui";
import { ComponentHealthTable } from "../features/components/ComponentHealthTable";
import { CopilotPanel } from "../features/copilot/CopilotPanel";
import { ActivityPanel } from "../features/incident/Activity";
import { ApprovalsPanel } from "../features/incident/Approvals";
import { DetailsPanel } from "../features/incident/Details";
import { FixPanel } from "../features/incident/Fix";
import { InventoryPanel } from "../features/inventory/InventoryPanel";
import { MachineThumb } from "../features/machine/MachinePhoto";
import "../features/machine/machine.css";
import { PartsViews } from "../features/machine/PartsViews";
import { SchedulePanel } from "../features/schedule/SchedulePanel";
import { WeekCalendar } from "../features/schedule/WeekCalendar";
import { IncidentCard } from "../features/incident/IncidentCard";
import { TechnicianPanel } from "../features/incident/Technician";
import { WhyPanel } from "../features/incident/Why";
import { TelemetryPanel } from "../features/telemetry/TelemetryPanel";
import { LiveStreamPanel } from "../features/livestream/LiveStreamPanel";
import { fmtNum, vsNormal } from "../lib/format";
import "./dashboard.css";

const TICK_MS = 450;
const TICK_STEPS = 2;

export function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [autonomy, setAutonomy] = useState<AutonomySettings | null>(null);
  const [machines, setMachines] = useState<MachineSummary[]>([]);
  const { machineId: routeId } = useParams();
  const navigate = useNavigate();
  const machineId = routeId ?? null;
  const setMachineId = (id: string) => navigate(`/machines/${id}`);
  const [detail, setDetail] = useState<MachineDetail | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryResponse | null>(null);
  const [incident, setIncident] = useState<IncidentView | null>(null);
  const [selectedComponent, setSelectedComponent] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [streamMode, setStreamMode] = useState<"live" | "replay">("live");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const playingRef = useRef(false);
  playingRef.current = playing;

  const refresh = useCallback(async (id: string) => {
    const [ms, d, t] = await Promise.all([api.machines(), api.machine(id), api.telemetry(id)]);
    setMachines(ms);
    setDetail(d);
    setTelemetry(t);
    setIncident(d.summary.open_incident_id ? await api.incident(d.summary.open_incident_id) : null);
    setError(null);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [h, ms, a] = await Promise.all([api.health(), api.machines(), api.autonomy()]);
        setHealth(h);
        setAutonomy(a);
        setMachines(ms);
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
      }
    })();
  }, []);

  useEffect(() => {
    if (!machineId) return;
    setPlaying(false);
    setSelectedComponent(null);
    refresh(machineId).catch((e) => setError(String(e)));
  }, [machineId, refresh]);

  const replay = useCallback(
    async (action: "reset" | "advance" | "seek" | "to_end", opts: { steps?: number; cursor?: number } = {}) => {
      if (!machineId) return;
      setBusy(true);
      try {
        const r = await api.replay(machineId, action, opts);
        const wasOpen = incident?.incident.id === r.triggered_incident_id;
        await refresh(machineId);
        if (r.triggered_incident_id) {
          setToast(wasOpen ? `${r.machine_id}: priority raised` : `${r.machine_id}: problem found`);
          if (playingRef.current) setPlaying(false);
        }
        if (r.cursor >= r.length - 1) setPlaying(false);
      } catch (e) {
        setPlaying(false);
        setError(e instanceof ApiError ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [machineId, refresh, incident],
  );

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => replay("advance", { steps: TICK_STEPS }), TICK_MS);
    return () => clearTimeout(t);
  }, [playing, telemetry, replay]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const onDecide = async (actionId: string, body: DecisionRequest) => {
    await api.decide(actionId, body);
    if (machineId) await refresh(machineId);
  };
  const onExecute = async (actionId: string) => {
    await api.execute(actionId);
    if (machineId) await refresh(machineId);
  };
  const toggleAutopilot = async () => {
    if (!autonomy) return;
    const next = await api.setAutonomy(autonomy.level === "autopilot" ? "advise" : "autopilot");
    setAutonomy(next);
    if (machineId) await refresh(machineId);
    setToast(next.level === "autopilot" ? "Autopilot on: GhostShift places parts orders itself" : "Autopilot off: people approve every order");
  };
  const resetAll = async () => {
    setPlaying(false);
    await api.resetDemo();
    if (machineId) await refresh(machineId);
  };

  const machine = detail?.machine;
  const healthMap = Object.fromEntries((detail?.component_health ?? []).map((h) => [h.component_id, h]));
  const affected = incident?.incident.affected_component_id ?? null;
  const pts = telemetry?.window.points;
  const nowIso = pts && pts.length ? pts[pts.length - 1].timestamp : null;
  // Changes whenever the replay moves or the incident's steps change, so calendar and inventory refetch.
  const opsKey = `${telemetry?.cursor}|${incident?.incident.updated_at}|${incident?.activity.length}|${incident?.actions.map((a) => a.status).join()}`;
  const select = (id: string) => setSelectedComponent((cur) => (cur === id ? null : id));

  return (
    <div className="app">
      <TopBar health={health} autonomy={autonomy} onToggleAutopilot={toggleAutopilot} onReset={resetAll} />
      <div className="layout">
        <aside className="sidebar" aria-label="Machines">
          <Link className="back-link" to="/">
            ← Floor plan
          </Link>
          <MachineList machines={machines} selected={machineId} onSelect={setMachineId} />
          {health && <Connections health={health} />}
        </aside>
        <main className="main" id="main">
          {error && (
            <div className="notice error" role="alert">
              <Icon name="alert" />
              <span>{error}</span>
            </div>
          )}
          {machine && detail && telemetry ? (
            <>
              <MachineHeader
                detail={detail}
                streamMode={streamMode}
                onToggleStreamMode={(m) => setStreamMode(m)}
              />
              <div className="columns">
                <div className="col-left">
                  {streamMode === "live" ? (
                    <LiveStreamPanel machineId={machine.id} />
                  ) : (
                    <TelemetryPanel
                      machine={machine}
                      telemetry={telemetry}
                      screening={detail.screening}
                      replay={{
                        playing,
                        busy,
                        onPlay: () => setPlaying(true),
                        onPause: () => setPlaying(false),
                        onStep: () => replay("advance", { steps: 4 }),
                        onJump: () => replay("seek"),
                        onEnd: () => replay("to_end"),
                        onReset: () => replay("reset"),
                        onSeek: (c) => replay("seek", { cursor: c }),
                      }}
                    />
                  )}
                  <Panel title="Parts" id="parts" bodyClass="panel-body parts-body">
                    <div className="assembly-wrap">
                      <PartsViews
                        drawing={machine.drawing}
                        components={machine.components}
                        health={healthMap}
                        affectedId={affected}
                        selectedId={selectedComponent}
                        onSelect={select}
                        actionVerb={incident?.incident.maintenance?.work_order.title.split(" ")[0]}
                      />
                    </div>
                    <div className="table-scroll">
                      <ComponentHealthTable
                        components={machine.components}
                        health={healthMap}
                        affectedId={affected}
                        selectedId={selectedComponent}
                        onSelect={select}
                      />
                    </div>
                  </Panel>
                  <WeekCalendar machineId={machine.id} now={nowIso} refreshKey={opsKey} />
                  <InventoryPanel refreshKey={opsKey} highlightSku={incident?.incident.maintenance?.proposed_part?.sku} />
                </div>
                <div className="col-right">
                  {incident ? (
                    <>
                      <IncidentCard view={incident} />
                      <ActivityPanel view={incident} />
                      <WhyPanel incident={incident.incident} machine={machine} />
                      <FixPanel view={incident} />
                      <SchedulePanel view={incident} refreshKey={opsKey} onChanged={() => machineId && refresh(machineId)} />
                      <ApprovalsPanel view={incident} onDecide={onDecide} onExecute={onExecute} />
                      <TechnicianPanel incidentId={incident.incident.id} notifications={incident.notifications} />
                      <DetailsPanel view={incident} />
                    </>
                  ) : (
                    <NoIncident detail={detail} />
                  )}
                  <CopilotPanel machineId={machine.id} incident={incident} />
                </div>
              </div>
            </>
          ) : (
            !error && <p className="muted">Loading…</p>
          )}
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

export function TopBar({
  health,
  autonomy,
  onToggleAutopilot,
  onReset,
}: {
  health: HealthResponse | null;
  autonomy: AutonomySettings | null;
  onToggleAutopilot: () => void;
  onReset: () => void;
}) {
  const on = autonomy?.level === "autopilot";
  const live = health?.providers.filter((p) => p.provider.real && p.configured).map((p) => p.provider.name) ?? [];
  return (
    <header className="topbar">
      <Wordmark />
      <span className="topbar-sep" />
      <span className="topbar-ctx">Austin DC-2</span>
      <span className="spacer" />
      {autonomy && (
        <button
          className="autopilot"
          role="switch"
          aria-checked={on}
          onClick={onToggleAutopilot}
          title="Autopilot lets GhostShift place parts orders itself (High priority, within the limit, part available in time). Work that needs lockout/tagout always waits for a supervisor."
        >
          <span className="track" aria-hidden>
            <span className="knob" />
          </span>
          <span className="label">Autopilot</span>
          <span className="hint">
            {on ? `orders parts up to ${autonomy.auto_order_limit_usd.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })}` : "people approve orders"}
          </span>
        </button>
      )}
      {health && (
        <span className="mode-chip" title={health.providers.map((p) => `${p.capability}: ${p.detail}`).join("\n")}>
          {live.length ? `Live: ${live.join(", ")}` : "Demo · simulated data"}
        </span>
      )}
      <button className="btn sm topbar-btn" onClick={onReset} title="Clear incidents and start over" aria-label="Reset">
        <Icon name="reset" /> <span className="label">Reset</span>
      </button>
    </header>
  );
}

function MachineList({ machines, selected, onSelect }: { machines: MachineSummary[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <nav>
      <p className="eyebrow side-title">Machines</p>
      <ul className="clean machine-list">
        {machines.map((m) => (
          <li key={m.id}>
            <button className={`machine-item ${m.id === selected ? "active" : ""}`} onClick={() => onSelect(m.id)} aria-current={m.id === selected}>
              <span className={`status-bar ${m.open_incident_tier ? `tier-bar-${m.open_incident_tier}` : `sev-${m.status}`}`} aria-hidden />
              <span className="mi-body">
                <span className="row">
                  <span className="mono strong nowrap">{m.id}</span>
                  <span className="spacer" />
                  {m.open_incident_tier ? <PriorityPill tier={m.open_incident_tier} short /> : <SeverityPill severity={m.status} />}
                </span>
                <span className="small mi-name">{m.display_name.replace(`${m.id} `, "")}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

const CAPABILITY_LABEL: Record<string, string> = {
  telemetry: "Sensor data",
  llm: "Summaries",
  parts_catalog: "Parts",
  procurement: "Ordering",
  work_orders: "Work orders",
  sms: "Text messages",
  voice: "Voice",
};

function Connections({ health }: { health: HealthResponse }) {
  return (
    <section className="connections" aria-label="Connections">
      <p className="eyebrow side-title">Connections</p>
      <ul className="clean">
        {health.providers.map((p) => (
          <li key={`${p.capability}-${p.provider.name}`} title={p.detail}>
            <span>{CAPABILITY_LABEL[p.capability] ?? p.capability}</span>
            <span className="spacer" />
            <span className={p.provider.real ? (p.configured ? "conn-live" : "conn-off") : "muted"}>
              {p.provider.real ? (p.configured ? "Live" : "Not set up") : p.provider.kind === "deterministic" ? "Built-in" : "Simulated"}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** One plain sentence about the machine's current state. */
function statusLine(d: DiagnosticsResult): string {
  const a = d.anomalies[0];
  if (!a) return "All sensors normal";
  const s = d.sensors.find((x) => x.sensor_id === a.sensor_id)!;
  const name = s.sensor_name.split(" (")[0];
  const limit = s.limit_state === "alert" || s.limit_state === "danger" ? `, over ${s.limit_state} limit` : "";
  return `${name} ${fmtNum(s.current_value)} ${s.unit}, ${vsNormal(s)} vs normal${limit}`;
}

function MachineHeader({
  detail,
  streamMode,
  onToggleStreamMode,
}: {
  detail: MachineDetail;
  streamMode: "live" | "replay";
  onToggleStreamMode: (m: "live" | "replay") => void;
}) {
  const m = detail.machine;
  return (
    <section className="machine-header">
      <MachineThumb drawing={m.drawing} />
      <div className="mh-title">
        <h1>
          <span className="mono">{m.id}</span> {m.display_name.replace(`${m.id} `, "")}
        </h1>
        <p className="small muted">
          {m.model} · {m.context.line}
        </p>
      </div>

      <div className="seg" role="group" aria-label="Data view">
        <button type="button" aria-pressed={streamMode === "live"} onClick={() => onToggleStreamMode("live")}>
          Live stream
        </button>
        <button type="button" aria-pressed={streamMode === "replay"} onClick={() => onToggleStreamMode("replay")}>
          60-hour replay
        </button>
      </div>

      <div className="mh-status">
        {detail.summary.open_incident_tier ? (
          <PriorityPill tier={detail.summary.open_incident_tier} />
        ) : (
          <SeverityPill severity={detail.summary.status} />
        )}
        <span className="small">{statusLine(detail.screening)}</span>
      </div>
    </section>
  );
}

function NoIncident({ detail }: { detail: MachineDetail }) {
  return (
    <Panel title="No open problems" id="no-incident">
      <p className="small muted">
        {detail.screening.severity === "normal"
          ? "Press Play to replay the last 60 hours, or skip straight to the fault."
          : "Something looks off. Step forward to run a full check."}
      </p>
    </Panel>
  );
}
