import type { Incident, Machine } from "../../api/types";
import { Panel, SeverityPill } from "../../components/ui";
import { fmtNum, vsNormal } from "../../lib/format";

const LIMIT_TEXT = { alert: "Over alert limit", danger: "Over danger limit" } as const;

export function WhyPanel({ incident, machine }: { incident: Incident; machine: Machine }) {
  const d = incident.diagnostics;
  const hyp = d.hypotheses[0];
  const assess = Object.fromEntries(d.sensors.map((s) => [s.sensor_id, s]));
  const part = (id: string) => machine.components.find((c) => c.id === id)?.name.toLowerCase() ?? id;

  return (
    <Panel title="Why it was flagged" id="why">
      <div className="stack">
        <ul className="clean signal-list">
          {d.anomalies.map((a) => {
            const s = assess[a.sensor_id];
            const limit = s.limit_state === "alert" || s.limit_state === "danger" ? LIMIT_TEXT[s.limit_state] : "Above normal range";
            return (
              <li key={a.evidence_id}>
                <div className="row">
                  <span className="small strong-ish">{s.sensor_name.split(" (")[0]}</span>
                  <span className="spacer" />
                  <SeverityPill severity={a.severity} label={limit} />
                </div>
                <div className="reading">
                  <span className="mono now">
                    {fmtNum(s.current_value)} <span className="xs muted">{s.unit}</span>
                  </span>
                  <span className="small muted">
                    normal {fmtNum(s.baseline.mean)} · {vsNormal(s)}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
        <p className="small">
          {hyp ? (
            <>
              This pattern matches <strong>{hyp.name.toLowerCase()}</strong> on the {part(hyp.component_id)}.
            </>
          ) : (
            "The readings don't match a known fault pattern."
          )}
        </p>
      </div>
    </Panel>
  );
}
