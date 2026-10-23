import type { Component, ComponentHealth, Incident, SensorAssessment } from "../../api/types";
import { SeverityPill } from "../../components/ui";
import { fmtHours, fmtNum, rulRange, vsNormal } from "../../lib/format";

interface Props {
  component: Component;
  health: ComponentHealth | null;
  incident: Incident;
}

/** Everything a technician needs about one part: condition, readings, replacement and service. */
export function PartCard({ component, health, incident }: Props) {
  const isAffected = component.id === incident.affected_component_id;
  const hyp = incident.diagnostics.hypotheses[0];
  // Readings from this part's own sensors, plus (for the flagged part) the signals that point to it.
  const ids = new Set(
    incident.diagnostics.sensors.filter((s) => s.component_id === component.id && s.role === "health").map((s) => s.sensor_id),
  );
  if (isAffected && hyp) hyp.signature_sensor_ids.forEach((id) => ids.add(id));
  const readings = incident.diagnostics.sensors.filter((s) => ids.has(s.sensor_id));
  const part = isAffected ? incident.maintenance?.proposed_part : null;
  const due = health?.remaining_service_interval.value_hours ?? null;

  return (
    <section className={`m-card part-card ${isAffected ? "is-affected" : ""}`} aria-live="polite">
      <div className="row">
        <h2 className="part-title">{component.name}</h2>
        <span className="spacer" />
        {health?.basis === "interval_only" ? (
          <span className="xs muted">No sensors</span>
        ) : (
          <SeverityPill severity={health?.status ?? "normal"} />
        )}
      </div>
      {component.description && <p className="xs muted">{component.description}</p>}

      {part && (
        <div className="replace">
          <div className="xs strong">Replace with</div>
          <div className="small">
            <span className="mono">{part.sku}</span> · {part.description}
          </div>
          <div className="xs muted">
            {(part.availability.on_hand ?? 0) > 0
              ? `${part.availability.on_hand} in stock at ${part.availability.location}`
              : `Not in stock · ${part.availability.lead_time_days} day lead time`}
          </div>
        </div>
      )}

      {readings.map((s) => (
        <Reading key={s.sensor_id} s={s} />
      ))}

      <dl className="part-facts">
        {health?.rul?.supportable && (
          <div>
            <dt>Time to danger limit</dt>
            <dd className="mono">{rulRange(health.rul)}</dd>
          </div>
        )}
        <div>
          <dt>Next service</dt>
          <dd className={`mono ${due !== null && due < 0 ? "warn-text" : ""}`}>{due === null ? "—" : due < 0 ? fmtHours(due) : `in ${fmtHours(due)}`}</dd>
        </div>
        <div>
          <dt>Last serviced</dt>
          <dd className="mono">{component.maintenance.last_service_at.slice(0, 10)}</dd>
        </div>
      </dl>
    </section>
  );
}

function Reading({ s }: { s: SensorAssessment }) {
  return (
    <div className="m-reading">
      <div className="row">
        <span className="small">{s.sensor_name.split(" (")[0]}</span>
        <span className="spacer" />
        {s.anomalous && <span className={`xs strong sev-text-${s.severity}`}>{vsNormal(s)} vs normal</span>}
      </div>
      <div className="row">
        <span className="mono big">{fmtNum(s.current_value)}</span>
        <span className="mono small muted">{s.unit}</span>
      </div>
      <div className="xs muted mono">
        normal {fmtNum(s.baseline.mean)}
        {s.alert_limit !== null && ` · alert ${fmtNum(s.alert_limit, 1)}`}
        {s.danger_limit !== null && ` · danger ${fmtNum(s.danger_limit, 1)}`}
      </div>
    </div>
  );
}
