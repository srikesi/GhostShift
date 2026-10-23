import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { ops, type Booking } from "../api/ops";
import type { AutonomySettings, HealthResponse, MachineSummary } from "../api/types";
import { Icon, Panel, SimTag } from "../components/ui";
import { MachineThumb } from "../features/machine/MachinePhoto";
import { FloorPlan, statusOf } from "../features/floorplan/FloorPlan";
import { getFloorPlan, type FloorPlanData } from "../features/floorplan/planApi";
import { fmtDateTime } from "../lib/format";
import { TopBar } from "./Dashboard";
import "./dashboard.css";
import "./home.css";

const POLL_MS = 4000;

/** Home: the site floor plan. Click a machine to open its page. */
export function HomePage() {
  const [plan, setPlan] = useState<FloorPlanData | null>(null);
  const [machines, setMachines] = useState<MachineSummary[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [autonomy, setAutonomy] = useState<AutonomySettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [ms, bs] = await Promise.all([api.machines(), ops.bookings().catch(() => [] as Booking[])]);
      setMachines(ms);
      setBookings(bs);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    getFloorPlan().then(setPlan, (e) => setError(String(e)));
    api.health().then(setHealth, () => undefined);
    api.autonomy().then(setAutonomy, () => undefined);
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  const toggleAutopilot = async () => {
    if (!autonomy) return;
    setAutonomy(await api.setAutonomy(autonomy.level === "autopilot" ? "advise" : "autopilot"));
  };
  const resetAll = async () => {
    await api.resetDemo();
    load();
  };

  const states = machines.map((m) => ({ m, st: statusOf(m) }));
  const attention = states.filter((s) => s.st.problem);
  const watching = states.filter((s) => !s.st.problem && s.m.status !== "normal");
  const normal = states.length - attention.length - watching.length;
  const next = [...bookings].sort((a, b) => a.start.localeCompare(b.start))[0];
  const placeholders = plan ? plan.units.filter((u) => !u.machine_id).length : 0;

  return (
    <div className="app">
      <TopBar health={health} autonomy={autonomy} onToggleAutopilot={toggleAutopilot} onReset={resetAll} />
      <main className="home" id="main">
        {error && (
          <div className="notice error" role="alert">
            <Icon name="alert" />
            <span>{error}</span>
          </div>
        )}
        <header className="home-head">
          <div>
            <h1>{plan?.site ?? "Austin DC-2"}</h1>
            <p className="small muted">Welcome back. Pick a machine to see how it is doing and who is on it.</p>
          </div>
          <ul className="clean summary" aria-label="Summary">
            <li className={attention.length ? "needs" : ""}>
              <strong>{attention.length}</strong> need attention
            </li>
            <li>
              <strong>{watching.length}</strong> watching
            </li>
            <li>
              <strong>{normal}</strong> normal
            </li>
          </ul>
        </header>

        {next && (
          <p className="small next-job">
            <Icon name="clock" /> Next job: {fmtDateTime(next.start)} · {next.technician_name} on {next.machine_id} <SimTag />
          </p>
        )}

        {plan ? (
          <Panel title={<>Floor plan <SimTag title="Simplified demo layout" /></>} id="plan" bodyClass="panel-body plan-body">
            <FloorPlan plan={plan} machines={machines} />
            <p className="xs muted plan-note">
              Solid tiles are monitored by GhostShift. Dashed tiles are placeholders: {placeholders} units with no data in this demo.
            </p>
          </Panel>
        ) : (
          !error && <p className="muted">Loading…</p>
        )}

        <Panel title="Machines" id="machines">
          <ul className="clean home-list">
            {states.map(({ m, st }) => (
              <li key={m.id}>
                <Link to={`/machines/${m.id}`} className={`home-row ${st.tone}`}>
                  <MachineThumb drawing={m.machine_type === "rack" ? "rack" : "chiller"} />
                  <span className="mono strong">{m.id}</span>
                  <span className="small">{m.display_name.replace(`${m.id} `, "")}</span>
                  <span className="spacer" />
                  <span className={`tag status ${st.tone}`}>
                    {st.word}
                    {st.problem ? " priority" : ""}
                  </span>
                </Link>
                <p className="xs muted">{m.status_note}</p>
              </li>
            ))}
          </ul>
        </Panel>
      </main>
    </div>
  );
}
